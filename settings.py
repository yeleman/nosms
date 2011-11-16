#!/usr/bin/env python
# encoding=utf-8
# maintainer: rgaudin

""" Configuration

* Host and Port for the HTTP server
* Connection and Device for Modem access """

# HTTP Server will listen for messages on default kannel path:
# http://localhost:1234/cgi-bin/sendsms?to=555555&text=Hello+world
LISTENING_PORT = 13013

# WARNING:
# If you are using gammu version < 1.29, you *need* to create a ~/.gammurc
# config file with your gammu config. NoSMS will read *first* entry.
# Example:
# [gammu]
# port=/dev/ttyUSB0
# connection=at

# Gammu connection protocol
# most modem are 'at'
CONNECTION = 'at115200'

# serial device to access modem
DEVICE = '/dev/ttyUSB0'

# white list of numbers to accept incoming SMS from.
# useful for filtering operator SPAM
# if you don't want filtering, just use r'^.*$'
NUMBER_REGEX = r'^\+223[76]\d{7}$'

# HTTP URL which will receive incoming SMS
# SMS are sent in a GET request like
# http://localhost:8000/sms?from=555555&text=Hello+world
SENDING_URL = 'https://pnlp.sante.gov.ml/nosms/'
