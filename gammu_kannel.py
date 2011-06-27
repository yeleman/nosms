#!/usr/bin/env python

'''
This is a very simple modem -> http gateway script. It depends only gammu:
    aptitude install python-gammu

It has its own wsgi webserver that listens for messages to be sent
out the modem and incoming messages received by the modem will be sent
to the specified http url.

The script will cleanly exit on KeyboardInterrupt

'''


import re
import threading
from wsgiref import simple_server
from urlparse import parse_qs
from time import sleep
from Queue import Queue, Empty
from urllib import urlencode, urlopen

import gammu

'''
The port this webserver will be listening to for messages
It presents the same interface as kannel. For example, if the port is 1234
then you can send a message out the modem by GETing:
    http://localhost:1234/cgi-bin/sendsms?to=555555&text=Hello+world
'''
LISTENING_PORT = 13013

# The gammu connection protocol- for a modem you almost certainly want 'at'
CONNECTION = 'at'

# Modem device
DEVICE = '/dev/ttyUSB0'

'''
A regex of phone numbers from which messages will be passed to the gateway.
This is important as sometimes you get a message from let's
say MTN with MTN as the identity.
You don't want to respond to that. Also, if you get a marketing
message from a short-code (let's say 8008) and you respond
"Can't understand your message...", it may respond:
"Can't understand your message" and hilarity ensues.
You could use this regex as a white-list.
'''
NUMBER_REGEX = r'^\+223[76]\d{7}$'

'''
The webserver to send incoming messages to. Right now it sends through GET
and the GET variable names are hard coded. Currenlty the script will try
to send messages to the another web server by GETing:
    http://localhost:8000/sms?from=555555&text=Hello+world
Important: The web server that this goes to must respond with http status code
202. That is the appropriate code for this sort of thing.
If it responds with anything other than 202 this script will not delete the SMS
from the SIM / Modem and it will continue trying to GET until it gets 202
'''
SENDING_URL = 'http://localhost:8000/nosms/'


class WsgiThread(threading.Thread):
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
    def __init__(self, kill, to_modem):
        threading.Thread.__init__(self, name='modem')
        self.kill = kill
        self.to_modem = to_modem
        self.sm = gammu.StateMachine()
        self.sm.SetConfig(0, {'Connection': CONNECTION, 'Device': DEVICE})
        self.regex = re.compile(NUMBER_REGEX)

    def delete(self, msg):
        try:
            self.sm.DeleteSMS(msg['Folder'], msg['Location'])
        except (gammu.ERR_EMPTY, gammu.ERR_INVALIDLOCATION):
            pass

    def run(self):
        self.sm.Init()
        while not self.kill.is_set():

            #Sending
            try:
                msg = to_modem.get_nowait()
            except Empty:
                pass
            else:
                msg['SMSC'] = {'Location': 1}
                try:
                    self.sm.SendSMS(msg)
                except gammu.ERR_UNKNOWN:
                    pass

            # Receiving
            try:
                msg = self.sm.GetNextSMS(0, True)[0]
            except gammu.ERR_EMPTY:
                pass
            else:
                if not self.regex.match(msg['Number']):
                    self.delete(msg)
                else:
                    try:
                        res = urlopen('%s?%s' \
                                      % (SENDING_URL, \
                                         urlencode({'from': msg['Number'], \
                                         'text': msg['Text']})))
                    except IOError:
                        pass
                    else:
                        if res.code == 202:
                            self.delete(msg)
            self.kill.wait(.5)
        try:
            self.sm.Terminate()
        except:
            pass

if __name__ == '__main__':
    to_modem = Queue()
    kill = threading.Event()

    modem = ModemThread(kill, to_modem)
    modem.start()
    wsgi = WsgiThread(to_modem)
    wsgi.start()

    while True:
        try:
            sleep(2)
        except KeyboardInterrupt:
            break
    kill.set()
    wsgi.server.shutdown()
    wsgi.join()
    modem.join()
