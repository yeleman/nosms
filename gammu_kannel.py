#!/usr/bin/env python
# encoding=utf-8
# maintainer: dgelvin, rgaudin

""" Kannel-like interface to a Modem using Gammu.

This script acts as a fake Kannel setup.
It answers to the same HTTP requests and forwards incoming SMS
to HTTP as well.

It depends only on python-gammu.

The script will cleanly exit on KeyboardInterrupt """

import re
import threading
from wsgiref import simple_server
from urlparse import parse_qs
from time import sleep
from Queue import Queue, Empty
from urllib import urlencode, urlopen
import logging
import random

import gammu

from nosms.settings import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
gammu_version = float(gammu.Version()[0].rpartition('.')[0])

logger.info(u"Gammu Version: %s" % gammu_version)


class WsgiThread(threading.Thread):
    """ HTTP Web Server receiving Outgoing SMS requests """
    def __init__(self, to_modem):
        threading.Thread.__init__(self, name='wsgi')
        self.to_modem = to_modem
        self.server = simple_server.make_server('', LISTENING_PORT, self.app)

    def run(self):
        self.server.serve_forever(poll_interval=0.5)

    def app(self, environ, start_response):
        ct = [('Content-Type', 'text/plain')]
        q_dict = parse_qs(environ['QUERY_STRING'])
        path = environ['PATH_INFO']
        if path == '/cgi-bin/sendsms' and 'to' in q_dict and 'text' in q_dict:
            start_response('202 ACCEPTED', ct)
            self.to_modem.put({'Number': q_dict['to'][0], \
                               'Text': q_dict['text'][0]})
        else:
            start_response('400 BAD REQUEST', ct)
        return ['']


class ModemThread(threading.Thread):
    """ Gammu query loop for sending/receiving SMS from Modem """
    def __init__(self, kill, to_modem):
        threading.Thread.__init__(self, name='modem')
        self.kill = kill
        # Outgoing SMS queue
        self.to_modem = to_modem
        self.sm = gammu.StateMachine()
        if gammu_version < 1.29:
            self.sm.ReadConfig(0, 0)
        else:
            self.sm.SetConfig(0, {'Connection': CONNECTION, 'Device': DEVICE})
        self.regex = re.compile(NUMBER_REGEX)
        # multipart messages store
        self.store = {}

    def delete(self, msg):
        """ delete an SMS from the Modem memory """
        try:
            self.sm.DeleteSMS(msg['Folder'], msg['Location'])
        except (gammu.ERR_EMPTY, gammu.ERR_INVALIDLOCATION):
            pass

    def msg_is_multipart(self, msg):
        """ is this message part of a multipart one ? """
        if 'MultiPart' in msg:
            return msg['MultiPart']
        try:
            return msg['UDH']['AllParts'] > 1
        except:
            return False

    def msg_is_unicode(self, msg):
        """ does this message needs to be sent as unicode ? """
        try:
            msg['Text'].encode('ascii')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return True
        else:
            return False

    def msg_multipart_id(self, msg):
        """ internal ID of the multipart message """
        return msg['UDH']['ID8bit']

    def msg_store_part(self, msg):
        """ stores part of a multipart message for later processing """
        msgid = self.msg_multipart_id(msg)
        if not msgid in self.store:
            self.store[msgid] = {'AllParts': msg['UDH']['AllParts'], \
                            'parts': {}, 'DateTime': msg['DateTime'], \
                            'Number': msg['Number']}
        self.store[msgid]['parts'][msg['UDH']['PartNumber']] = msg['Text']

    def msg_is_complete(self, msg):
        """ if this message complete ? All parts retrieved ? """
        if not self.msg_is_multipart(msg):
            return True

        msgid = self.msg_multipart_id(msg)
        if not msgid in self.store:
            return False
        if self.store[msgid]['parts'].keys().__len__() == \
                                                 self.store[msgid]['AllParts']:
            return True
        return False

    def msg_unified(self, msg):
        """ a concatenated message representing all parts of a multipart """
        msgid = self.msg_multipart_id(msg)
        text = []
        for i in range(1, self.store[msgid]['AllParts'] + 1):
            text.append(self.store[msgid]['parts'][i])
        return {'Number': self.store[msgid]['Number'], \
                   'DateTime': self.store[msgid]['DateTime'], \
                   'Text': u"".join(text), \
                   'MultiPart': True, \
                   'ID': msgid}

    def msg_delete_multipart(self, msg):
        """ remove multipart message from internal store """
        del(self.store[msg['ID']])

    def run(self):
        self.sm.Init()
        while not self.kill.is_set():

            # sending outgoing messages
            try:
                # retrieve a message from outgoing queue
                msg = to_modem.get_nowait()
            except Empty:
                pass
            else:
                # important to know length and type of message
                text = msg['Text'].decode('utf-8')
                number = msg['Number']
                is_unicode = self.msg_is_unicode(msg)
                length = text.__len__()

                logger.info(u"OUTGOING [%d] %s message: %s" \
                            % (length, u"unicode" \
                                       if is_unicode \
                                       else u"ascii", \
                               text))

                # single ascii SMS
                # max_length of 160 chars.
                if not is_unicode and length <= 160:
                    encoded = [msg]
                # multipart, ascii SMS.
                # will be split in 153 chars long SMS.
                elif not is_unicode and length > 160:
                    smsinfo = {'Class': 1, \
                               'Unicode': False, \
                               'Entries': [{'ID': 'ConcatenatedTextLong', \
                                            'Buffer': text}]}
                    encoded = gammu.EncodeSMS(smsinfo)
                # single unicode SMS.
                # max_length of 70 chars.
                elif is_unicode and length <= 70:
                    smsinfo = {'Class': 1, \
                               'Unicode': True, \
                               'Entries': [{'ID': 'ConcatenatedTextLong', \
                                            'Buffer': text}]}
                    encoded = gammu.EncodeSMS(smsinfo)
                # multipart unicode SMS
                # will be split in 63 chars long SMS.
                else:
                    smsinfo = {'Class': 1, \
                               'Unicode': True, \
                               'Entries': [{'ID': 'ConcatenatedTextLong', \
                                            'Buffer': text}]}
                    encoded = gammu.EncodeSMS(smsinfo)

                # loop on parts
                for msg in encoded:
                    msg['SMSC'] = {'Location': 1}
                    msg['Number'] = number

                    try:
                        logger.debug(u"Sending SMS: %s" % msg)
                        self.sm.SendSMS(msg)
                    except gammu.ERR_UNKNOWN:
                        pass

            # receiving incoming messages
            try:
                # get first SMS from Modem
                msg = self.sm.GetNextSMS(0, True)[0]
            except gammu.ERR_EMPTY:
                pass
            else:
                logger.debug(u"Received SMS: %s" % msg)

                # remove SMS from modem and move-on if not in white-list
                if not self.regex.match(msg['Number']):
                    self.delete(msg)
                else:
                    # if SMS is a part of a multipart SMS
                    # store the part and remove SMS from Modem.
                    if self.msg_is_multipart(msg):
                        self.msg_store_part(msg)
                        self.delete(msg)

                    # if SMS is a single message or was last part of a
                    # multipart message
                    if self.msg_is_complete(msg):
                        # builf concatenated multipart if required
                        if self.msg_is_multipart(msg):
                            msg = self.msg_unified(msg)

                        try:
                            logger.info(u"INCOMING [%d] from %s: %s" \
                            % (msg['Text'].__len__(), \
                               msg['Number'], msg['Text']))

                            # submit message to application
                            res = urlopen('%s?%s' \
                                          % (SENDING_URL, \
                                            urlencode({'from': msg['Number'], \
                                             'text': msg['Text']})))
                        except IOError:
                            # we don't do anything so modem will find
                            # the SMS again next time
                            pass
                        else:
                            if res.code == 202:
                                # application received the SMS
                                # delete multipart from internal store
                                if self.msg_is_multipart(msg):
                                    self.msg_delete_multipart(msg)
                                else:
                                    # delete SMS from modem
                                    self.delete(msg)
            # main loop 500ms
            self.kill.wait(.5)
        try:
            # close modem connection properly
            self.sm.Terminate()
        except:
            pass

if __name__ == '__main__':
    logger.info(u"Starting %s" % __name__)
    to_modem = Queue()
    kill = threading.Event()

    logger.info(u"\tstarting modem...")
    modem = ModemThread(kill, to_modem)
    modem.start()
    logger.info(u"\tstarting web server...")
    wsgi = WsgiThread(to_modem)
    wsgi.start()

    while True:
        try:
            sleep(2)
        except KeyboardInterrupt:
            logger.info(u"Exiting.")
            break
    kill.set()
    wsgi.server.shutdown()
    wsgi.join()
    modem.join()
