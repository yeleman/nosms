======
NoSMS
======

NoSMS is a lightweight django application providing SMS functionnality.
It interacts natively with Kannel (SMPP) or Gammu (Modem).

Requirements
------------

* python-gammu
* Django

Documentation
-------------

NoSMS is based on a regular Django model storing messages.
A message has a text, identity, direction and status.

Messages status are: created, processed, error.
Every 'created' message will be added to the send/process list.

Processed messages are never accessed and could be removed safely.
Error messages are message which triggered an exception or problem during
processing. Those are considered processed and won't be accessed again.

When NoSMS knows the problem is temporary, it leaves messages as created
for later processing.

NoSMS respond to Kannel interface only:
- receives incoming SMS as GET request from Kannel
- sends outgoing SMS as GET request to Kannel

This is implemented with:
- URL rule to receive messages in your Django configuration
- Django management command to loop on outgoing SMS submission.

Usage
-----
::

    # create new message from scratch
    x = Message(identity="21345678", text="Hello World")
    x.send()

    # create sms using helper
    from nosms.utils import send_sms
    send_sms("9893812", "Hello World")

    # example handler
    def myhandler(message):
        if message.text.startwith('hello'):
            message.respond("Thanks %s" % message.identity)
            message.status = Message.STATUS_PROCESSED
            message.save()
            return True
        return False


Configuration
--------------

#. Add NOSMS specific config variables to your settings.py file:

::

    # your SMS handler
    # A function which take a nosms.models.Message object as parameter
    NOSMS_HANDLER = 'myapp.myhandler'

    # Kannel configuration
    # username and password are optionnal if you are using Gammu
    NOSMS_TRANSPORT_HOST = 'localhost'
    NOSMS_TRANSPORT_PORT = 13013
    #NOSMS_TRANSPORT_USERNAME = None
    #NOSMS_TRANSPORT_PASSWORD = None

#. Add the URL pattern to your urls.py file:

::

    (r'^nosms/', include('nosms.urls')),

#. Launch the outgoing message command

::

    ./manage.py nosmsloop

