#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import time
import logging
import locale

from django.core.management.base import BaseCommand, CommandError

from nosms.models import Message
from nosms.utils import process_outgoing_message, process_incoming_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
locale.setlocale(locale.LC_ALL, settings.DEFAULT_LOCALE)


def next_message():
    """ next to-be-sent message from DB """
    try:
        return Message.outgoing.filter(status=Message.STATUS_CREATED).all()[0]
    except IndexError:
        return None


class Command(BaseCommand):

    def handle(self, *args, **options):

        logger.info("Launching NOSMS main loop")

        incoming = Message.incoming.filter(status=Message.STATUS_CREATED).all()
        if incoming.count() > 0:
            logger.info(u"Dispatching %d unhandled " \
                        "incoming messages" % incoming.count())
            for message in incoming:
                try:
                    process_incoming_message(message)
                    message.status = Message.STATUS_PROCESSED
                    message.save()
                except:
                    pass

        logger.info(u"Waiting for outgoing message to be sent...")
        while True:
            message = next_message()
            if message:
                logger.info("Sending out Message: %s" % message)
                try:
                    process_outgoing_message(message)
                except Exception as e:
                    logger.error("Unable to send %s with %r" % (message, e))
                    message.status = Message.STATUS_ERROR
                    message.save()
                else:
                    message.status = Message.STATUS_PROCESSED
                    message.save()
            try:
                time.sleep(2)
            except KeyboardInterrupt:
                break
