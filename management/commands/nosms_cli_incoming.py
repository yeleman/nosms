#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import locale
import time
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import translation
from django.db import connection, transaction
from django.db import connections

from nosms.models import Message
from nosms.utils import process_incoming_message, import_path

logger = logging.getLogger(__name__)
locale.setlocale(locale.LC_ALL, settings.DEFAULT_LOCALE)


class Command(BaseCommand):

    def handle(self, *args, **options):

        translation.activate(settings.DEFAULT_LOCALE)

        # Arguments are sender message
        if len(args) != 2:
            logger.warning(u"No message or senderID provided\n" \
                           u"Format is senderID \"message text\"")
            return False
        msg_sender = unicode(args[0])
        msg_str = unicode(args[1])

        message = Message(identity=msg_sender, \
                          text=msg_str,
                          status=Message.STATUS_CREATED, \
                          direction=Message.DIRECTION_INCOMING)
        message.save()
        message.date = datetime.now()
        message.save()

        try:
            handler_func = import_path(settings.NOSMS_HANDLER)
        except AttributeError:
            message.status = Message.STATUS_ERROR
            message.save()
            logger.error(u"NO SMS_HANDLER defined while receiving SMS")
        except Exception as e:
            message.status = Message.STATUS_ERROR
            message.save()
            logger.error(u"Unbale to call SMS_HANDLER with %r" % e)
        else:
            try:
                handler_func(message)
            except Exception as e:
                message.status = Message.STATUS_ERROR
                message.save()
                logger.error(u"SMS handler failed on %s with %r" \
                             % (message, e))

        translation.deactivate()
