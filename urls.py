#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import os

from django.conf.urls.defaults import patterns, include, url
from nosms import views

urlpatterns = patterns('',
    url(r'(?P<identity>[a-z0-9\+\.\-\_]+)/(?P<text>.*)$', \
        views.handler, name='handler'),
    url(r'$', \
        views.handler_get, name='handler_get'),
)
