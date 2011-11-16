#!/bin/bash
#maintainer: rgaudin

# ussd.sh
# prints the response of an USSD request.

# 1. checks if Gammu smsd is running and kill it if it is.
# 2. use Gammu client to make USSD request.
# 3. parses Gammu answer to print only USSD answer.
# 4. restart smsd if killed on 1.

# configuration
USSD_CODE=$1
INIT="lsb" # upstart | none
SMSD_PID_FILE=/tmp/smsd.pid
SMSD_CONF=/etc/gammu-smsdrc
SMSD_RELAUNCH=0

# get defaults parameters from system
if [ -f /etc/default/nosms ]
then
    source /etc/default/nosms
fi

if [ "$USSD_CODE" = "" ]
then
    echo "No USSD code provided."
    exit 1
fi

kill_if_running() {
    if [ -f $SMSD_PID_FILE ]
    then
        SMSD_PID=`cat $SMSD_PID_FILE`
        if [ -n $SMSD_PID ]
        then
            if [ -d "/proc/$SMSD_PID" ]
            then
                RELAUNCH=1
                kill $SMSD_PID
                sleep 1
            fi
        fi
    fi
}

if [ "$INIT" = "none" ]
then
    kill_if_running
elif [ "$INIT" = "lsb" ]
then
    sudo service gammu-smsd stop &> /dev/null
else
    sudo stop gammu-smsd &> /dev/null
fi

# make USSD request via Gammu.
export USSD_STR=`gammu --getussd $USSD_CODE`

# Parse output with Python.
FORMATTED_STR=`python -c "import os
import re
ussd_string = os.environ['USSD_STR'].strip().split(\"\n\")[-1]
try:
    ussd_string = re.split(r'^Service reply\s*:\s', ussd_string)[-1]
except:
    pass
if ussd_string[0] == '\"' and ussd_string[-1] == '\"':
    ussd_string = ussd_string[1:-1]
print(ussd_string)"`

export USSD_STR=

# relaunch smsd if we killed it.
if [ "$SMSD_RELAUNCH" = "1" ]
then
    if [ "$INIT" = "none" ]
    then
        gammu-smsd -c $SMSD_CONF -d -p $SMSD_PID_FILE
    elif [ "$INIT" = "lsb" ]
    then
        sudo service gammu-smsd start &> /dev/null
    else
        sudo start gammu-smsd &> /dev/null
    fi
fi

# print result.
echo $FORMATTED_STR

export FORMATTED_STR=
