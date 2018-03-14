#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
# jupyter - Launch an interactive Jupyter session
# Copyright (C) 2003-2018  The MiG Project lead by Brian Vinter
#
# This file is part of MiG.
#
# MiG is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# MiG is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
# -- END_HEADER ---
#

"""Automatic home drive mount from jupyter
This backend makes two requests to the target url specified by the
configuration.jupyter_url variable the first requests authenticates against the
jupyterhub server, it passes the Remote-User header with the client_id's email.
The second request takes the newly instantiated ssh keyset and passes it to the
jupyterhub server via the Mig-Mount header.
Subsequently any potentially old keysets for this user is removed and the new
keyset is commited to the users configuration.jupyter_mount_files_dir
directory. Finally this active keyset is linked to the directory where the sftp
will check for a valid keyset and the users homedrive is linked to the same
location.

Finally the user is redirected to the jupyterhub home page where a new notebook
server can be instantiated and mount the users linked homedrive with the passed
keyset.
"""

import os
import socket
import sys
import requests
import time
import shutil
import shared.returnvalues as returnvalues
from shared.conf import get_configuration_object
from binascii import hexlify
from shared.base import client_id_dir
from shared.functional import validate_input_and_cert
from shared.defaults import session_id_bytes
from shared.httpsclient import unescape
from shared.init import initialize_main_variables
from shared.ssh import generate_ssh_rsa_key_pair
from shared.fileio import make_symlink, pickle, unpickle, write_file


# TODO: Validate that this actually works
def is_active(pickle_state, timeout=7200):
    """
    :param pickle_state: expects a pickle object dictionary that
    contains the field 'CREATED_TIMESTAMP' with a timestamp of when the pickle
    was established
    :param timeout: seconds in which the pickle_state is considered active
    default is 2 hours -> 7200 seconds
    :return: Boolean
    """
    assert type(pickle_state) is dict, "pickle_state is a dictionary: %r" % \
                                pickle_state
    assert pickle_state.has_key('CREATED_TIMESTAMP')

    active = True
    active_time = int(time.time()) \
                  - int(pickle_state['CREATED_TIMESTAMP'])
    if active_time > timeout:
        active = False
    return active


def remove_jupyter_mount(jupyter_mount_path, configuration):
    """
    :param jupyter_mount_path path to a jupyter mount pickle state file
    :param configuration the MiG configuration object
    :return: void
    """

    filename = os.path.basename(jupyter_mount_path)
    link_home = configuration.sessid_to_jupyter_mount_link_home
    # Remove jupyter mount session symlinks for the default sftp service
    for link in os.listdir(link_home):
        if link in filename:
            os.remove(os.path.join(link_home, link))

    # Remove subsys sftp files
    if configuration.site_enable_sftp_subsys:
        auth_dir = os.path.join(configuration.mig_system_files,
                                  'jupyter_mount')
        for auth_file in os.listdir(auth_dir):
            if auth_file.split('.authorized_keys')[0] in filename:
                os.remove(os.path.join(auth_dir, auth_file))

    # Remove old pickle state file
    os.remove(jupyter_mount_path)


def prune_jupyter_mounts(jupyter_mounts, configuration):
    """
    If multiple jupyter mounts are active, remove every except for the
    latests one
    :param active_jupyter_mounts: list of jupyter mount pickle state paths
    :param configuration the MiG configuration object
    :return: a list containing only
    """
    latest = jupyter_mounts[0]
    for mount_file in jupyter_mounts:
        jupyter_dict = unpickle(mount_file, configuration)
        latest_dict = unpickle(latest, configuration)
        if int(latest_dict['CREATED_TIMESTAMP']) \
                < int(jupyter_dict['CREATED_TIMESTAMP']):
            remove_jupyter_mount(latest, configuration)
            latest = mount_file

    jupyter_mounts.clear()
    jupyter_mounts.append(latest)


def jupyter_host(configuration, output_objects, user):
    """
    Returns the users jupyterhub host
    :param configuration: the MiG Configuration object
    :param output_objects:
    :param user: the user identifier used in the Remote-User header to
    authenticate against the jupyterhub server
    :return: output_objects and a 200 OK status for the webserver to return
    to the client
    """
    configuration.logger.info("User: %s finished, redirecting to the jupyter host" % user)
    status = returnvalues.OK
    home = configuration.jupyter_base_url
    headers = [('Location', home), ('Remote-User', user)]
    output_objects.append({'object_type': 'start', 'headers': headers})
    return (output_objects, status)


def reset():
    """
    Helper function to clean up all jupyter directories and mounts
    :return:
    """
    configuration = get_configuration_object()
    auth_path = os.path.join(configuration.mig_system_files,
                               'jupyter_mount')
    mnt_path = configuration.jupyter_mount_files_dir
    link_path = configuration.sessid_to_jupyter_mount_link_home
    if os.path.exists(auth_path):
        shutil.rmtree(auth_path)

    if os.path.exists(mnt_path):
        shutil.rmtree(mnt_path)

    if os.path.exists(link_path):
        shutil.rmtree(link_path)


def signature():
    """Signature of the main function"""
    defaults = {}
    return ['', defaults]


def main(client_id, user_arguments_dict):
    """Main function used by front end"""

    (configuration, logger, output_objects, op_name) = \
        initialize_main_variables(client_id, op_header=False)
    client_dir = client_id_dir(client_id)
    defaults = signature()[1]
    (validate_status, accepted) = validate_input_and_cert(
        user_arguments_dict,
        defaults,
        output_objects,
        client_id,
        configuration,
        allow_rejects=False,
    )

    if not validate_status:
        return (accepted, returnvalues.CLIENT_ERROR)

    logger.info("User: %s executing %s" % (client_id, op_name))

    if not configuration.site_enable_jupyter:
        output_objects.append({'object_type': 'error_text', 'text':
            '''The Jupyter service is not enabled on the system'''})
        return (output_objects, returnvalues.SYSTEM_ERROR)

    if not configuration.site_enable_sftp_subsys and not \
            configuration.site_enable_sftp:
        output_objects.append({'object_type': 'error_text', 'text':
            '''The required sftp service is not enabled on the system'''})
        return (output_objects, returnvalues.SYSTEM_ERROR)

    # Test target jupyter url
    session = requests.session()
    try:
        session.get(configuration.jupyter_url)
    except requests.ConnectionError as err:
        logger.error("Failed to establish connection to %s error %s",
                    configuration.jupyter_url, err)
        output_objects.append(
            {'object_type': 'error_text',
             'text': '''Failed to establish connection to the Jupyter service'''})
        return (output_objects, returnvalues.CLIENT_ERROR)

    remote_user = unescape(os.environ.get('REMOTE_USER', '')).strip()
    if remote_user == '':
        logger.error("Can't connect to jupyter with an empty REMOTE_USER "
                     "environment variable")
        output_objects.append(
            {'object_type': 'error_text',
             'text': '''Failed to establish connection to the Jupyter service'''})
        return (output_objects, returnvalues.CLIENT_ERROR)

    # Regular sftp path
    mnt_path = os.path.join(configuration.jupyter_mount_files_dir, client_dir)
    # Subsys sftp path
    subsys_path = os.path.join(configuration.mig_system_files,
                               'jupyter_mount')
    # sftp session path
    link_home = configuration.sessid_to_jupyter_mount_link_home

    # Preparing prerequisites
    if not os.path.exists(mnt_path):
        os.makedirs(mnt_path)

    if not os.path.exists(link_home):
        os.makedirs(link_home)

    if configuration.site_enable_sftp_subsys:
        if not os.path.exists(subsys_path):
            os.makedirs(subsys_path)

    url_mount = configuration.jupyter_url + '/mount'

    # Does the client home dir contain an active mount key
    # If so just keep on using it.
    jupyter_mount_files = [os.path.join(mnt_path, jfile) for jfile in
                           os.listdir(mnt_path)
                           if jfile.endswith('.jupyter_mount')]

    logger.debug("User: %s mount files: %s", client_id,
                "\n".join(jupyter_mount_files))
    logger.debug("Remote-User %s", remote_user)
    active_mounts = []
    for jfile in jupyter_mount_files:
        jupyter_dict = unpickle(jfile, logger)
        # Remove not active keys
        if not is_active(jupyter_dict, timeout=10):
            remove_jupyter_mount(jfile, configuration)
        else:
            active_mounts.append(jfile)

    logger.debug("User: %s active keys: %s", client_id,
                "\n".join(active_mounts))
    # If multiple are active, remove oldest
    if len(active_mounts) > 1:
        prune_jupyter_mounts(active_mounts, configuration)
        if len(active_mounts) != 1:
            logger.error("After pruning jupyter keys %s are still active",
                         len(active_mounts))

    # A valid active key is already present redirect straight to the jupyter
    # service, pass most recent mount information
    if len(active_mounts) == 1:
        # Check whether the user should authenticate and pass mount information
        auth_mount_header = {'Remote-User': remote_user, 'Mig-Mount': str(
            active_mounts[0])}

        session = requests.session()
        # Provide the active homedrive mount information
        session.get(url_mount, headers=auth_mount_header)

        # Redirect client to jupyterhub
        return jupyter_host(configuration, output_objects, remote_user)

    # Create a new keyset
    # Create login session id
    sessionid = hexlify(open('/dev/urandom').read(session_id_bytes))

    # Create ssh rsa keya and known_hosts
    mount_private_key = ""
    mount_public_key = ""
    mount_known_hosts = ""

    # Generate private/public keys
    (mount_private_key, mount_public_key) = generate_ssh_rsa_key_pair()

    # Known hosts
    sftp_addresses = socket.gethostbyname_ex(
        configuration.user_sftp_show_address or socket.getfqdn())

    # Subsys sftp support
    if configuration.site_enable_sftp_subsys:
        # Restrict possible mount agent
        auth_content = []
        restrict_opts = 'no-agent-forwarding,no-port-forwarding,no-pty,'
        restrict_opts += 'no-user-rc,no-X11-forwarding'
        restrictions = '%s' % restrict_opts
        auth_content.append('%s %s\n' % (restrictions, mount_public_key))
        # Write auth file
        write_file('\n'.join(auth_content),
                   os.path.join(subsys_path, sessionid
                                + '.authorized_keys'), logger, umask=027)

    mount_known_hosts = "%s,[%s]:%s" % (sftp_addresses[0],
                                        sftp_addresses[0],
                                        configuration.user_sftp_show_port)

    logger.debug("User: %s - Creating a new jupyter mount keyset - "
                 "private_key: %s public_key: %s ", client_id,
                mount_private_key, mount_public_key)

    jupyter_dict = {}
    jupyter_dict['MOUNT_HOST'] = configuration.short_title
    jupyter_dict['SESSIONID'] = sessionid
    jupyter_dict['USER_CERT'] = client_id
    # don't need fraction precision, also not all systems provide fraction
    # precision.
    jupyter_dict['CREATED_TIMESTAMP'] = int(time.time())
    jupyter_dict['MOUNTSSHPRIVATEKEY'] = mount_private_key
    jupyter_dict['MOUNTSSHPUBLICKEY'] = mount_public_key
    # Used by the jupyterhub to know which host to mount against
    jupyter_dict['TARGET_MOUNT_ADDR'] = "@" + sftp_addresses[0] + ":"

    # Only post the required keys
    transfer_dict = {key: jupyter_dict[key] for key in ('MOUNT_HOST',
                                                       'SESSIONID',
                                                       'MOUNTSSHPRIVATEKEY',
                                                       'TARGET_MOUNT_ADDR')}

    logger.debug("User: %s Mig-Mount header: %s", client_id, jupyter_dict)

    # Auth and pass a new set of valid mount keys
    url_mount = configuration.jupyter_url + '/mount'
    auth_mount_header = {'Remote-User': remote_user,
                         'Mig-Mount': str(transfer_dict)}

    # First login
    session = requests.session()
    # Provide homedrive mount information
    session.get(url_mount, headers=auth_mount_header)

    # Update pickle with the new valid key
    jupyter_mount_state_path = os.path.join(mnt_path,
                                            sessionid + '.jupyter_mount')

    pickle(jupyter_dict, jupyter_mount_state_path, logger)

    # Link jupyter pickle state file
    linkdest_new_jupyter_mount = os.path.join(mnt_path,
                                                  sessionid + '.jupyter_mount')

    linkloc_new_jupyter_mount = os.path.join(link_home,
                                             sessionid + '.jupyter_mount')
    make_symlink(linkdest_new_jupyter_mount, linkloc_new_jupyter_mount, logger)

    # Link userhome
    linkdest_user_home = os.path.join(configuration.user_home, client_dir)
    linkloc_user_home = os.path.join(link_home, sessionid)
    make_symlink(linkdest_user_home, linkloc_user_home, logger)

    return jupyter_host(configuration, output_objects, remote_user)


if __name__ == "__main__":
    if not os.environ.get('MIG_CONF', ''):
        conf_path = os.path.join(os.path.dirname(sys.argv[0]),
                                 '..', '..', 'server', 'MiGserver.conf')
        os.environ['MIG_CONF'] = conf_path
    request_uri = "/dag/user/rasmus.munk@nbi.ku.dk"
    if sys.argv[1:]:
        if sys.argv[1] == 'reset':
            reset()
            exit(0)
        request_uri = sys.argv[1]
    os.environ['REQUEST_URI'] = request_uri
    query_string = ''
    if sys.argv[2:]:
        query_string = sys.argv[2]
    os.environ['QUERY_STRING'] = query_string
    client_id = "/C=DK/ST=NA/L=NA/O=NBI/OU=NA/CN=Rasmus Munk/emailAddress=rasmus.munk@nbi.ku.dk"
    if sys.argv[3:]:
        client_id = sys.argv[3]
    os.environ['SSL_CLIENT_S_DN'] = client_id
    print main(client_id, {})
