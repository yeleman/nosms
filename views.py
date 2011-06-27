#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import urllib
import thread
import logging

from django.http import HttpResponse, Http404
from django.shortcuts import redirect
from django.conf import settings

from models import Message

logger = logging.getLogger(__name__)


def import_path(name):
    modname, _, attr = name.rpartition('.')
    if not modname:
        # name was just a single module name
        return __import__(attr)
    m = __import__(modname, fromlist=[attr])
    return getattr(m, attr)


def handler_get(request):
    if request.method == 'GET':
        if 'from' in request.GET and 'text' in request.GET:
            return redirect('handler', request.GET.get('from'), \
                            request.GET.get('text'))
    raise Http404(u"Oh nooozzee")


def handler(request, identity, text):

    def _str(uni):
        try:
            return str(uni)
        except:
            return uni.encode('utf-8')

    def _plus(str):
        return str.replace('%2B', '+')

    text = urllib.unquote(_str(_plus(text.replace('+', ' '))))

    message = Message(identity=identity, text=text, \
                      status=Message.STATUS_CREATED, \
                      direction=Message.DIRECTION_INCOMING)
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
            thread.start_new_thread(handler_func, (message,))
        except Exception as e:
            message.status = Message.STATUS_ERROR
            message.save()
            logger.error(u"SMS handler failed on %s with %r" % (message, e))

    return HttpResponse(u"Thanks %s, the following message " \
                        "have been processed:\n%s" % (identity, text), \
                        mimetype='text/plain', status=202)
