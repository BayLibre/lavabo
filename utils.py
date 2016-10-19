#! /usr/bin/python2

#  Copyright 2016 Quentin Schulz <quentin.schulz@free-electrons.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

import StringIO
import os
import ConfigParser
import device
import sqlite3
import json
import fcntl
import time
import ssl
import urlparse
import xmlrpclib

def get_device_list(db_conn, devices_conf_dir):
    devices = {}

    for conf_file in os.listdir(devices_conf_dir):
        if conf_file.startswith("."):
            continue
        config_parser = ConfigParser.ConfigParser()
        conf = StringIO.StringIO()
        conf.write('[__main__]\n')
        conf.write(open(os.path.join(devices_conf_dir, conf_file)).read())
        conf.seek(0)
        config_parser.readfp(conf)
        try:
            device_name = config_parser.get("__main__", "hostname")
            reset_command = config_parser.get("__main__", "hard_reset_command")
            off_command = config_parser.get("__main__", "power_off_cmd")
            serial_command = config_parser.get("__main__", "connection_command")
            devices[device_name] = device.Device(device_name, reset_command, off_command, serial_command)
            db_cursor = db_conn.cursor()
            try:
                db_cursor.execute("INSERT INTO devices VALUES (?)", (device_name,))
                db_cursor.execute("INSERT INTO reservations VALUES (?, ?, ?, ?)", (device_name, 0, None, 0))
                db_conn.commit()
            except sqlite3.IntegrityError:
                pass
            finally:
                db_cursor.close()
        except ConfigParser.NoOptionError:
            pass
    return devices

def create_json(status, content):
    return {"status": status, "content": content}

def create_answer(status, content):
    return json.dumps(create_json(status, content))

def acquire_lock(lock, tries=5):
    for i in range(0,tries):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except IOError:
            if i == tries-1:
                return False
            time.sleep(0.1)
    return True

def release_lock(lock):
    fcntl.flock(lock, fcntl.LOCK_UN)

# Taken from: https://github.com/kernelci/lava-ci/blob/master/lib/utils.py
def validate_input(username, token, server):
    url = urlparse.urlparse(server)
    if url.path.find('RPC2') == -1:
        print "LAVA Server URL must end with /RPC2"
        sys.exit(1)
    return url.scheme + '://' + username + ':' + token + '@' + url.netloc + url.path

def connect(url):
    try:
        if 'https' in url:
            context = hasattr(ssl, '_create_unverified_context') and ssl._create_unverified_context() or None
            connection = xmlrpclib.ServerProxy(url, transport=xmlrpclib.SafeTransport(use_datetime=True, context=context))
        else:
            connection = xmlrpclib.ServerProxy(url)
        return connection
    except (xmlrpclib.ProtocolError, xmlrpclib.Fault, IOError) as e:
        print "Unable to connect to %s" % url
        sys.exit(1)

def init_db():
    db_conn = sqlite3.connect("remote-control.db")
    db_cursor = db_conn.cursor()
    db_cursor.execute("CREATE TABLE IF NOT EXISTS users (username PRIMARY KEY)")
    db_cursor.execute("CREATE TABLE IF NOT EXISTS devices (hostname PRIMARY KEY)")
    db_cursor.execute("CREATE TABLE IF NOT EXISTS reservations (device_name, last_use INTEGER, made_by, reserved INTEGER, FOREIGN KEY(device_name) REFERENCES devices(hostname), FOREIGN KEY(made_by) REFERENCES users(username))")
    db_conn.commit()
    db_cursor.close()
    return db_conn
