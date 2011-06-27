#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import urllib
import thread
import logging

from django.http import HttpResponse, Http404
from django.shortcuts import redirect

from nosms.models import Message
from nosms.utils import process_incoming_message

logger = logging.getLogger(__name__)


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

    process_incoming_message(message)

    return HttpResponse(u"Thanks %s, the following message " \
                        "have been processed:\n%s" % (identity, text), \
                        mimetype='text/plain', status=202)
