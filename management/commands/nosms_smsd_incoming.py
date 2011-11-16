#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import locale
import time
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db import connections

from nosms.models import Message
from nosms.utils import process_incoming_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
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
            logger.warning("No message ID provided")
            return False
        try:
            sql_id = int(args[0])
        except:
            sql_id = None

        if not isinstance(sql_id, int):
            logger.error("Provided ID (%s) is not an int." % sql_id)
            return False

        # open up smsd DB
        cursor = connections['smsd'].cursor()
        cursor.execute("SELECT ReceivingDateTime, SenderNumber, " \
                       "TextDecoded FROM inbox WHERE " \
                       "ID = %s AND Processed = %s", [sql_id, 'false'])
        msg_data = dictfetchone(cursor)
        if not msg_data:
            logger.warning("No unprocessed row in DB for ID %d" % sql_id)
            return False
        message = Message(identity=msg_data['SenderNumber'], \
                          text=msg_data['TextDecoded'],
                          status=Message.STATUS_CREATED, \
                          direction=Message.DIRECTION_INCOMING)
        message.save()
        message.date = msg_data['ReceivingDateTime']
        message.save()

        process_incoming_message(message)

        cursor.execute("UPDATE inbox SET Processed = 'true' " \
                       "WHERE ID = %s", [sql_id])
        transaction.commit_unless_managed(using='smsd')
