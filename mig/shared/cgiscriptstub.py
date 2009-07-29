#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
# cgiscriptstub - [insert a few words of module description on this line]
# Copyright (C) 2003-2009  The MiG Project lead by Brian Vinter
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

"""Interface between CGI and functionality"""

import cgi
import cgitb
cgitb.enable()

from shared.cgiinput import fieldstorage_to_dict
from shared.cgishared import init_cgi_script_with_cert, \
    init_cgiscript_possibly_with_cert

from shared.output import do_output


def run_cgi_script(main, delayed_input=None, print_header=True,
                   content_type='text/html'):
    """Get needed information and run the function received as argument.
    If delayed_input is not set to a function, the default cgi input will be
    extracted and parsed before being passed on to the main function. Some
    CGI operations like file upload won't work efficiently if the fieldstorage
    is passed around (huge memory consumption) so they can pass the form
    extracting function here and leave it to the back end to extract the
    form.
    """

    (logger, configuration, client_id, o) = init_cgi_script_with_cert(
        print_header, content_type)

    if not delayed_input:
        fieldstorage = cgi.FieldStorage()
        user_arguments_dict = fieldstorage_to_dict(fieldstorage)
    else:
        user_arguments_dict = {'__DELAYED_INPUT__': delayed_input}
    (out_obj, (ret_code, ret_msg)) = main(client_id,
            user_arguments_dict)

    # default to html

    output_format = 'html'
    if user_arguments_dict.has_key('output_format'):
        output_format = user_arguments_dict['output_format'][0]

    output = do_output(ret_code, ret_msg, out_obj, output_format)
    if not output:

        # Error occured during output print

        print 'Return object was _not_ successfully printed!'
    print output


def run_cgi_script_possibly_with_cert(main, delayed_input=None,
                                      print_header=True,
                                      content_type='text/html'):
    """Get needed information and run the function received as argument.
    If delayed_input is not set to a function, the default cgi input will be
    extracted and parsed before being passed on to the main function. Some
    CGI operations like file upload won't work efficiently if the fieldstorage
    is passed around (huge memory consumption) so they can pass the form
    extracting function here and leave it to the back end to extract the
    form.
    """

    (logger, configuration, client_id, o) = \
        init_cgiscript_possibly_with_cert(print_header, content_type)

    if not delayed_input:
        fieldstorage = cgi.FieldStorage()
        user_arguments_dict = fieldstorage_to_dict(fieldstorage)
    else:
        user_arguments_dict = {'__DELAYED_INPUT__': delayed_input}
    (out_obj, (ret_code, ret_msg)) = main(client_id,
            user_arguments_dict)

    # default to html

    output_format = 'html'
    if user_arguments_dict.has_key('output_format'):
        output_format = user_arguments_dict['output_format'][0]

    output = do_output(ret_code, ret_msg, out_obj, output_format)
    if not output:

        # Error occured during output print

        print 'Return object was _not_ successfully printed!'
    print output


