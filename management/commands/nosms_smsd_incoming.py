#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import thread
import locale
import time
#import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db import connections

from nosms.models import Message
from nosms.utils import process_incoming_message, import_path

#logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
#handler = logging.StreamHandler()
#logger.addHandler(handler)
locale.setlocale(locale.LC_ALL, settings.DEFAULT_LOCALE)


def dictfetchall(cursor):
    "Returns all rows from a cursor as a dict"
    desc = cursor.description
    return [
        dict(zip([col[0] for col in desc], row))
        for row in cursor.fetchall()
    ]


def dictfetchone(cursor):
    "Returns one row from a cursor as a dict"
    desc = cursor.description
    row = cursor.fetchone()
    if not row:
        return None
    return dict(zip([col[0] for col in desc], row))


class Command(BaseCommand):

    def handle(self, *args, **options):

        # Message ID in DB is provided as first argument
        if len(args) != 1:
            #logger.warning("No message ID provided")
            print("WARN: No message ID provided")
            return False
        try:
            sql_id = int(args[0])
        except:
            sql_id = None

        if not isinstance(sql_id, int):
            #logger.error("Provided ID (%s) is not an int." % sql_id)
            print("ERROR: Provided ID (%s) is not an int." % sql_id)
            return False

        # open up smsd DB
        cursor = connections['smsd'].cursor()
        cursor.execute("SELECT ReceivingDateTime, SenderNumber, " \
                       "TextDecoded FROM inbox WHERE " \
                       "ID = %s AND Processed = %s", [sql_id, 'false'])
        msg_data = dictfetchone(cursor)
        if not msg_data:
            #logger.warning("No unprocessed row in DB for ID %d" % sql_id)
            print("WARN: No unprocessed row in DB for ID %d" % sql_id)
            return False
        message = Message(identity=msg_data['SenderNumber'], \
                          text=msg_data['TextDecoded'],
                          status=Message.STATUS_CREATED, \
                          direction=Message.DIRECTION_INCOMING)
        message.save()
        message.date = msg_data['ReceivingDateTime']
        message.save()

        # for some reason it's buggy
        #process_incoming_message(message)
        try:
            handler_func = import_path(settings.NOSMS_HANDLER)
        except AttributeError:
            message.status = Message.STATUS_ERROR
            message.save()
            #logger.error(u"NO SMS_HANDLER defined while receiving SMS")
            print(u"ERROR: NO SMS_HANDLER defined while receiving SMS")
        except Exception as e:
            message.status = Message.STATUS_ERROR
            message.save()
            #logger.error(u"Unbale to call SMS_HANDLER with %r" % e)
            print(u"ERROR: Unbale to call SMS_HANDLER with %r" % e)
        else:
            try:
                thread.start_new_thread(handler_func, (message,))
            except Exception as e:
                message.status = Message.STATUS_ERROR
                message.save()
                #logger.error(u"SMS handler failed on %s with %r" % (message, e))
                print(u"ERROR: SMS handler failed on %s with %r" % (message, e))

        cursor.execute("UPDATE inbox SET Processed = 'true' " \
                       "WHERE ID = %s", [sql_id])
        transaction.commit_unless_managed(using='smsd')
