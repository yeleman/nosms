#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

from django.contrib import admin

from models import Message


class MessageAdmin(admin.ModelAdmin):
    list_display = ('identity', 'date', 'direction', \
                    'get_status_display', 'text')
    list_filter = ['direction', 'status']
    search_fields = ['identity', 'text']
    date_hierarchy = 'date'

admin.site.register(Message, MessageAdmin)
