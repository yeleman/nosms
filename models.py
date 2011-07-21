#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

from django.db import models
from django.utils.translation import ugettext, ugettext_lazy as _


class OutgoingManager(models.Manager):

    def get_query_set(self):
        return super(OutgoingManager, self).get_query_set() \
                        .filter(direction=Message.DIRECTION_OUTGOING)


class IncomingManager(models.Manager):
    '''
    A custom manager for LoggedMessage that limits query sets to
    incoming messages only.
    '''

    def get_query_set(self):
        return super(IncomingManager, self).get_query_set() \
                        .filter(direction=Message.DIRECTION_INCOMING)


class Message(models.Model):

    class Meta:
        verbose_name = _(u"Message")
        verbose_name_plural = _(u"Messages")
        ordering = ['-date', 'direction']

    DIRECTION_INCOMING = 'I'
    DIRECTION_OUTGOING = 'O'

    DIRECTION_CHOICES = (
        (DIRECTION_INCOMING, _(u"Incoming")),
        (DIRECTION_OUTGOING, _(u"Outgoing")))

    STATUS_CREATED = '0'
    STATUS_PROCESSED = '1'
    STATUS_ERROR = '2'

    STATUS_CHOICES = (
        (STATUS_CREATED, _(u"Created")),
        (STATUS_PROCESSED, _(u"Processed")),
        (STATUS_ERROR, _(u"Error")))

    identity = models.CharField(max_length=25)
    text = models.CharField(max_length=1000)
    date = models.DateTimeField(_(u"date"), auto_now_add=True)
    direction = models.CharField(_(u"type"), max_length=1,
                                 choices=DIRECTION_CHOICES,
                                 default=DIRECTION_OUTGOING)
    status = models.CharField(_(u"status"), max_length=1,
                              choices=STATUS_CHOICES, default=STATUS_CREATED)

    # django manager first
    objects = models.Manager()
    incoming = IncomingManager()
    outgoing = OutgoingManager()

    def __unicode__(self):
        return  u"%(direction)s - %(ident)s - %(text)s" % \
                 {'direction': self.get_direction_display(),
                  'ident': self.identity,
                  'text': self.text}

    def get_direction_display(self):
        for direction, name in Message.DIRECTION_CHOICES:
            if direction == self.direction:
                return name
        return _(u"Unknown")

    def get_status_display(self):
        for status, name in Message.STATUS_CHOICES:
            if status == self.status:
                return name
        return _(u"Unknown")

    def is_incoming(self):
        return self.direction == self.DIRECTION_INCOMING

    def to_dict(self):
        return {'id': self.id, 'message': self.text, \
                     'status': self.status, \
                     'dateStr': self.date.strftime("%d-%b-%Y @ %H:%M:%S"), \
                     'identity': self.identity}

    def send(self):
        self.direction = self.DIRECTION_OUTGOING
        self.status = self.STATUS_CREATED
        self.save()

    def respond(self, text):
        m = Message(identity=self.identity, text=text, \
                    direction=self.DIRECTION_OUTGOING, \
                    status=self.STATUS_CREATED)
        m.save()
