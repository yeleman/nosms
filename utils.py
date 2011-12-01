#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

import re
import urllib
import time
#import logging
#import logging.handlers
import thread
import random

import gammu

from django.conf import settings
from django.db import connection, transaction
from django.db import connections

from models import Message

#logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
#handler = logging.StreamHandler()
#logger.addHandler(handler)


def import_path(name):
    """ import a callable from full module.callable name """
    modname, _, attr = name.rpartition('.')
    if not modname:
        # single module name
        return __import__(attr)
    m = __import__(modname, fromlist=[attr])
    return getattr(m, attr)


def send_sms(to, text):
    """ create arbitrary message for sending """
    m = Message(identity=to, text=text)
    m.direction = Message.DIRECTION_OUTGOING
    m.status = Message.STATUS_CREATED
    m.save()


def process_incoming_message(message):
    """ call handler on message """
    try:
        handler_func = import_path(settings.NOSMS_HANDLER)
    except AttributeError:
        message.status = Message.STATUS_ERROR
        message.save()
        #logger.error(u"NO SMS_HANDLER defined while receiving SMS")
        print(u"ERROR: NO SMS_HANDLER defined while receiving SMS")
    except Exception as e:
        message.status = Message.STATUS_ERROR
        message.save()
        #logger.error(u"Unbale to call SMS_HANDLER with %r" % e)
        print(u"ERROR: Unbale to call SMS_HANDLER with %r" % e)
    else:
        try:
            thread.start_new_thread(handler_func, (message,))
        except Exception as e:
            message.status = Message.STATUS_ERROR
            message.save()
            #logger.error(u"SMS handler failed on %s with %r" % (message, e))
            print(u"ERROR: SMS handler failed on %s with %r" % (message, e))


def random_udh(length):
    """ random alnum string """
    return '050003' + hex(random.randint(0, 255))
    return ''.join([random.choice('abcdefghijklmnopqrstuvwxyz1234567890') \
                        for i in range(length)])


def message_to_parts(message):
    CODING_UNICODE = 'Unicode_No_Compression'
    CODING_DEFAULT = 'Default_No_Compression'
    MAX_LEN = 160
    UMAX_LEN = 70
    CREATOR = 'nosms'

    text = message.text
    udh = random_udh(8)
    is_unicode = msg_is_unicode(text)
    length = text.__len__()
    first_part = {'DestinationNumber': message.identity,
                  'Coding': '',
                  'TextDecoded': '',
                  'MultiPart': '',
                  'UDH': '%s0101' % udh,
                  'CreatorID': CREATOR}
    if not is_unicode and length <= MAX_LEN:
        # msg is short ascii text. create single
        first_part['Coding'] = CODING_DEFAULT
        first_part['TextDecoded'] = text
        first_part['MultiPart'] = 'false'
        return [first_part,]
    elif is_unicode and length <= UMAX_LEN:
        # msg is short unicode. create single
        first_part['Coding'] = CODING_UNICODE
        first_part['TextDecoded'] = text
        first_part['MultiPart'] = 'false'
        return [first_part,]
    else:
        # msg have to be multipart
        first_part['MultiPart'] = 'true'

        # find out first part
        stub = text[:MAX_LEN]
        if not msg_is_unicode(stub):
            first_part['Coding'] = CODING_DEFAULT
            first_part['TextDecoded'] = stub
            parts_text = text[MAX_LEN:]
        else:
            first_part['Coding'] = CODING_UNICODE
            first_part['TextDecoded'] = text[:UMAX_LEN]
            parts_text = text[UMAX_LEN:]

        parts = []
        seq = 1
        while parts_text:
            # create part for each chunk
            seq += 1
            part = {'Coding': '', 'TextDecoded': '',
                    'SequencePosition': seq, 'UDH': udh}
            stub = parts_text[:MAX_LEN]
            if not msg_is_unicode(stub):
                part['Coding'] = CODING_DEFAULT
                part['TextDecoded'] = stub
                parts_text = parts_text[MAX_LEN:]
            else:
                part['Coding'] = CODING_UNICODE
                part['TextDecoded'] = parts_text[:UMAX_LEN]
                parts_text = parts_text[UMAX_LEN:]
            parts.append(part)

    all_parts = [first_part] + parts
    parts_num = all_parts.__len__()

    # adjust UDH for multipart
    for i in range(0, parts_num):
        all_parts[i]['UDH'] = '%s%s%s' \
                              % (udh, str(parts_num).zfill(2), str(i + 1).zfill(2))

    return all_parts

def process_outgoing_message(message):
    """ fires a kannel-compatible HTTP request to send message """

    def process_smsd_inject(message):
        smsd = gammu.SMSD(settings.NOSMS_SMSD_CONF)
        msg = to_gammu(message)
        try:
            #logger.debug(u"Sending SMS: %s" % message)
            print(u"DEBUG: Sending SMS: %s" % message)
            smsd.InjectSMS([msg])
            message.status = Message.STATUS_PROCESSED
            message.save()
        except gammu.ERR_UNKNOWN as e:
            message.status = Message.STATUS_ERROR
            message.save()
            #logger.error(e)
            print(u"ERROR %s" % e)


    def process_smsd(message):
        cursor = connections['smsd'].cursor()

        parts = message_to_parts(message)

        # create message (first part)
        part = parts[0]
        cursor.execute("INSERT INTO outbox (DestinationNumber, Coding, " \
                       "TextDecoded, MultiPart, CreatorID, UDH) " \
                       "VALUES (%s, %s, %s, %s, %s, %s)",
                       [part['DestinationNumber'], part['Coding'],
                       part['TextDecoded'], part['MultiPart'],
                       part['CreatorID'], part['UDH']])
        transaction.commit_unless_managed(using='smsd')

        if parts.__len__() > 1:
            msg_id = cursor.lastrowid

            for i in range(1, parts.__len__() - 1):
                part = parts[i]
                cursor.execute("INSERT INTO outbox_multipart " \
                               "(ID, Coding, TextDecoded, " \
                               "SequencePosition, UDH) " \
                               "VALUES (%s, %s, %s, %s, %s)", [msg_id,
                               part['Coding'], part['TextDecoded'],
                               part['SequencePosition'], part['UDH']])
                transaction.commit_unless_managed(using='smsd')

    def process_kannel_like(message):
        def _str(uni):
            try:
                return str(uni)
            except:
                return uni.encode('utf-8')

        # remove non digit from number
        identity = re.compile('\D').sub("", message.identity)

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
            #logger.error("Error sending message: %s" % err)
            print("Error sending message: %s" % err)

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

            #logger.debug("message %s: %s" % (kw, message))
            print("DEBUG: message %s: %s" % (kw, message))
            message.status = Message.STATUS_PROCESSED
            message.save()

        # temporary error
        elif res.code == 503:
            #logger.error("message failed to send (temporary error): %s" % ans)
            print("ERROR: message failed to send (temporary error): %s" % ans)
            message.status = Message.STATUS_CREATED
            message.save()
        else:
            #logger.error("message failed to send: %s" % ans)
            print("ERROR: message failed to send: %s" % ans)
            message.status = Message.STATUS_ERROR
            message.save()

    if settings.NOSMS_TRANSPORT.lower() == 'smsd':
        process_smsd(message)
    else:
        process_kannel_like(message)


def msg_is_unicode(text):
        """ does this message needs to be sent as unicode ? """
        try:
            text.encode('ascii')
        except (UnicodeEncodeError, UnicodeDecodeError):
            return True
        else:
            return False


def to_gammu(message, msgclass=1):
    """ converts NoSMS message to Gammu msg """

    # important to know length and type of message
    try:
        text = message.text.decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        text = message.text
    number = message.identity
    is_unicode = msg_is_unicode(text)
    length = text.__len__()

    #logger.info(u"OUTGOING [%d] %s message: %s" \
    print(u"INFO: OUTGOING [%d] %s message: %s" \
                % (length, u"unicode" \
                           if is_unicode \
                           else u"ascii", \
                   text))

    # single ascii SMS
    # max_length of 160 chars.
    if not is_unicode and length <= 160:
        encoded = [{'Number': number, 'Text': text}]
    # multipart, ascii SMS.
    # will be split in 153 chars long SMS.
    elif not is_unicode and length > 160:
        smsinfo = {'Class': msgclass, \
                   'Unicode': False, \
                   'Entries': [{'ID': 'ConcatenatedTextLong', \
                                'Buffer': text}]}
        encoded = gammu.EncodeSMS(smsinfo)
    # single unicode SMS.
    # max_length of 70 chars.
    elif is_unicode and length <= 70:
        smsinfo = {'Class': msgclass, \
                   'Unicode': True, \
                   'Entries': [{'ID': 'ConcatenatedTextLong', \
                                'Buffer': text}]}
        encoded = gammu.EncodeSMS(smsinfo)
    # multipart unicode SMS
    # will be split in 63 chars long SMS.
    else:
        smsinfo = {'Class': msgclass, \
                   'Unicode': True, \
                   'Entries': [{'ID': 'ConcatenatedTextLong', \
                                'Buffer': text}]}
        encoded = gammu.EncodeSMS(smsinfo)

    # loop on parts
    for msg in encoded:
        msg['SMSC'] = {'Location': 1}
        msg['Number'] = number

    return msg


def get_ussd(ussd):

    import os
    import subprocess

    ussd_bin = os.path.join(os.path.dirname(__file__), 'ussd.sh')
    if not hasattr(subprocess, 'check_output'):
        ussd_string = subprocess.Popen([ussd_bin, ussd],
                                     stdout=subprocess.PIPE).communicate()[0]
    else:
        ussd_string = subprocess.check_output([ussd_bin, ussd]).strip().strip()

    return ussd_string
