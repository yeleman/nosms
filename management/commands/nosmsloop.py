#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import re
import urllib
import time
import logging

from django.conf import settings
from django.utils.translation import ugettext as _
from django.core.management.base import BaseCommand, CommandError

from nosms.models import Message

logger = logging.getLogger(__name__)


def send_message_to_transport(message):
    """ fires a kannel-compatible HTTP request to send message """

    def _str(uni):
        try:
            return str(uni)
        except:
            return uni.encode('utf-8')

    # remove non digit from number
    identity = re.compile('\D').sub("", msg.identity)

    # urlencode for HTTP get
    message_text = msg_enc = urllib.quote(_str(message.text))

    # send HTTP GET request to Kannel
    try:
        url = "http://%s:%d/cgi-bin/sendsms?" \
              "to=%s&from=&text=%s" \
              % (settings.NOSMS_TRANSPORT_HOST, \
                 settings.NOSMS_TRANSPORT_PORT, \
                 identity, message_text)
        # if there is a username/password, append to URL
        try:
            url = "%s&username=%s&password=%s" \
                  % (url, settings.NOSMS_TRANSPORT_USERNAME, \
                     settings.NOSMS_TRANSPORT_PASSWORD)
        except:
            pass
        res = urllib.urlopen(url)
        ans = res.read()
    except Exception, err:
        logger.error("Error sending message: %s" % err)

        # we'll try to send it again later
        message.status = Message.STATUS_CREATED
        message.save()
        return False

    # success
    if res.code == 202:
        if ans.startswith('0: Accepted'):
            kw = 'sent'
        elif ans.startswith('3: Queued'):
            kw = 'queued'
        else:
            kw = 'sent'

        logger.debug("message %s: %s" % (kw, message))
        message.status = Message.STATUS_PROCESSED
        message.save()

    # temporary error
    elif res.code == 503:
        logger.error("message failed to send (temporary error): %s" % ans)
        message.status = Message.STATUS_CREATED
        message.save()
    else:
        logger.error("message failed to send: %s" % ans)
        message.status = Message.STATUS_ERROR
        message.save()
    return True


def next_message():
    """ next to-be-sent message from DB """
    try:
        return Message.outgoing.filter(status=Message.STATUS_CREATED).all()[0]
    except IndexError:
        return None


class Command(BaseCommand):

    def handle(self, *args, **options):

        while True:
            message = next_message()
            if message:
                logger.info("Sending out Message: %s" % message)
                try:
                    send_message_to_transport(message)
                except Exception as e:
                    logger.error("Unable to send %s with %r" %(message, e))
                    message.status = Message.STATUS_ERROR
                    message.save()
                else:
                    message.status = Message.STATUS_PROCESSED
                    message.save()
            try:
                time.sleep(2)
            except KeyboardInterrupt:
                break
