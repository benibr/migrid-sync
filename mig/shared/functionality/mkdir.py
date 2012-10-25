#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
# mkdir - create directory in user hom
# Copyright (C) 2003-2011  The MiG Project lead by Brian Vinter
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

"""Emulate the un*x function with the same name"""

import os

import shared.returnvalues as returnvalues
from shared.base import client_id_dir
from shared.functional import validate_input_and_cert, REJECT_UNSET
from shared.handlers import correct_handler
from shared.init import initialize_main_variables
from shared.parseflags import parents, verbose
from shared.validstring import valid_user_path


def signature():
    """Signature of the main function"""

    defaults = {
        'path': REJECT_UNSET,
        'current_dir': [''],
        'flags': [''],
        'mkdirbutton': [''],
        }
    return ['', defaults]


def main(client_id, user_arguments_dict):
    """Main function used by front end"""

    (configuration, logger, output_objects, op_name) = \
        initialize_main_variables(client_id)
    client_dir = client_id_dir(client_id)
    status = returnvalues.OK
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

    if not correct_handler('POST'):
        output_objects.append(
            {'object_type': 'error_text', 'text'
             : 'Only accepting POST requests to prevent unintended updates'})
        return (output_objects, returnvalues.CLIENT_ERROR)

    flags = ''.join(accepted['flags'])
    patterns = accepted['path']
    current_dir = accepted['current_dir'][-1]

    # Please note that base_dir must end in slash to avoid access to other
    # user dirs when own name is a prefix of another user name

    base_dir = os.path.abspath(os.path.join(configuration.user_home,
                               client_dir)) + os.sep

    if verbose(flags):
        for flag in flags:
            output_objects.append({'object_type': 'text', 'text'
                                  : '%s using flag: %s' % (op_name,
                                  flag)})

    for pattern in patterns:

        # Check directory traversal attempts before actual handling to avoid
        # leaking information about file system layout while allowing
        # consistent error messages
        # NB: Globbing disabled on purpose here

        unfiltered_match = [base_dir + os.sep + current_dir + os.sep
                             + pattern]
        match = []
        for server_path in unfiltered_match:
            real_path = os.path.abspath(server_path)
            if not valid_user_path(real_path, base_dir, True):

                # out of bounds - save user warning for later to allow
                # partial match:
                # ../*/* is technically allowed to match own files.

                logger.warn('%s tried to %s %s restricted path! (%s)'
                            % (client_id, op_name, real_path, pattern))
                continue
            match.append(real_path)

        # Now actually treat list of allowed matchings and notify if no
        # (allowed) match

        if not match:
            output_objects.append(
                {'object_type': 'error_text', 'text'
                 : "%s: cannot create directory '%s': Permission denied"
                 % (op_name, pattern)})
            status = returnvalues.CLIENT_ERROR

        for real_path in match:
            relative_path = real_path.replace(base_dir, '')
            if verbose(flags):
                output_objects.append({'object_type': 'file', 'name'
                        : relative_path})
            if not parents(flags) and os.path.exists(real_path):
                output_objects.append({'object_type': 'error_text',
                        'text': '%s: path exist!' % pattern})
                status = returnvalues.CLIENT_ERROR
                continue

            try:
                if parents(flags):
                    if not os.path.isdir(real_path):
                        os.makedirs(real_path)
                else:
                    os.mkdir(real_path)
            except Exception, exc:
                output_objects.append({'object_type': 'error_text',
                        'text': "%s: '%s': %s" % (op_name,
                        relative_path, exc)})
                logger.error("%s: failed on '%s': %s" % (op_name,
                             relative_path, exc))

                status = returnvalues.SYSTEM_ERROR
                continue

    return (output_objects, status)


