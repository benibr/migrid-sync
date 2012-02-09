#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
# adminre - [insert a few words of module description on this line]
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

"""Create runtime environment"""

import base64

import shared.returnvalues as returnvalues
from shared.functional import validate_input_and_cert
from shared.init import initialize_main_variables
from shared.refunctions import is_runtime_environment, \
    list_runtime_environments, get_re_dict
from shared.rekeywords import get_keywords_dict


def signature():
    """Signature of the main function"""

    defaults = {
        're_template': [''],
        'software_entries': [1],
        'environment_entries': [1],
        'testprocedure_entry': [0],
        }
    return ['html_form', defaults]


def main(client_id, user_arguments_dict):
    """Main function used by front end"""

    (configuration, logger, output_objects, op_name) = \
        initialize_main_variables(client_id, op_header=False)
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
    re_template = accepted['re_template'][-1].upper()
    software_entries = int(accepted['software_entries'][-1])
    environment_entries = int(accepted['environment_entries'][-1])
    testprocedure_entry = int(accepted['testprocedure_entry'][-1])

    template = False
    if re_template:
        if not is_runtime_environment(re_template, configuration):
            output_objects.append(
                {'object_type': 'error_text', 'text'
                 : "re_template ('%s') is not a valid existing runtime env!"
                 % re_template})
            return (output_objects, returnvalues.CLIENT_ERROR)

        (template, msg) = get_re_dict(re_template, configuration)
        if not template:
            output_objects.append({'object_type': 'error_text', 'text'
                                   : 'Could not read re_template %s. %s'
                                   % (re_template, msg)})
            return (output_objects, returnvalues.SYSTEM_ERROR)

    # Avoid DoS, limit number of software_entries

    max_software_entries = 40
    if software_entries > max_software_entries:
        output_objects.append(
            {'object_type': 'error_text', 'text'
             : 'Maximum number of software_entries %s exceeded (%s)' % \
             (max_software_entries, software_entries)})
        return (output_objects, returnvalues.CLIENT_ERROR)

    # Avoid DoS, limit number of environment_entries

    max_environment_entries = 40
    if environment_entries > max_environment_entries:
        output_objects.append(
            {'object_type': 'error_text', 'text'
             : 'Maximum number of environment_entries %s exceeded (%s)' % \
             (max_environment_entries, environment_entries)})
        return (output_objects, returnvalues.CLIENT_ERROR)

    rekeywords_dict = get_keywords_dict()
    output_objects.append({'object_type': 'header', 'text'
                          : 'Create runtime environment'})
    (status, ret) = list_runtime_environments(configuration)
    if not status:
        output_objects.append({'object_type': 'error_text', 'text'
                              : ret})
        return (output_objects, returnvalues.SYSTEM_ERROR)

    output_objects.append({'object_type': 'text', 'text'
                          : 'Use existing RE as template'})

    html_form = \
        """<form method="get" action="adminre.py">
    <select name="re_template">
    <option value="">None

    """
    for existing_re in ret:
        html_form += '<option value=%s>%s\n' % (existing_re,
                existing_re)
    html_form += \
        """</select>
    <input type="submit" value="Get" />
    </form>"""
    output_objects.append({'object_type': 'html_form', 'text'
                          : html_form})

    output_objects.append(
        {'object_type': 'text', 'text'
         : '''Note that a runtime environment can not be changed or removed
when it has been created, so please be careful when filling in the details'''
         })
    output_objects.append(
        {'object_type': 'text', 'text'
         : '''Changing the number of software and environment entries removes
all data in the form, so please enter the correct values before entering any
information.'''
         })

    html_form = \
        """<form method='get' action='adminre.py'>
    <table border=0>
"""
    if template:
        if template.has_key('SOFTWARE'):
            software_entries = len(template['SOFTWARE'])
    html_form += """
<tr>
    <td>Number of needed software entries</td>
    <td><input type=text size=2 name=software_entries value=%s /></td>
</tr>""" % software_entries
    if template:
        if template.has_key('ENVIRONMENTVARIABLE'):
            environment_entries = len(template['ENVIRONMENTVARIABLE'])
    html_form += """
<tr>
    <td>Number of environment entries</td>
    <td><input type=text size=2 name=environment_entries value=%s /></td>
</tr>""" % environment_entries
    if template:
        if template.has_key('TESTPROCEDURE'):
            testprocedure_entry = 1
        else:
            testprocedure_entry = 0
    output_objects.append({'object_type': 'html_form', 'text'
                          : html_form})
    if testprocedure_entry == 0:
        select_string = \
            """<option value=0 selected>No<option value=1>Yes"""
    elif testprocedure_entry == 1:
        select_string = \
            """<option value=0>No<option value=1 selected>Yes"""
    else:
        output_objects.append(
            {'object_type': 'error_text', 'text'
             : 'testprocedure_entry should be 0 or 1, you specified %s'
             % testprocedure_entry})
        return (output_objects, returnvalues.CLIENT_ERROR)

    html_form = """
<tr>
    <td>Runtime environment has a testprocedure</td>
    <td><select name=testprocedure_entry>%s</select></td>
</tr>
<tr>
<td><input type='submit' value='Update fields' /></td>
</tr>
</table>
</form><br />
""" % select_string

    html_form += """
<form method='post' action='createre.py'>
<b>RE Name</b><br />
<small>(eg. DALTON-3.0, must be unique):</small><br />
<input type='text' size=40 name='re_name' /><br />
<br /><b>Description:</b><br />
<textarea cols='50' rows='2' wrap='off' name='redescription'>
"""
    if template:
        html_form += template['DESCRIPTION']
    html_form += '</textarea>'

    if template:
        if template.has_key('SOFTWARE'):
            soft_list = template['SOFTWARE']
            if soft_list:
                html_form += '<br /><b>Needed Software:</b><br />'
            for soft in soft_list:
                html_form += """
<textarea cols='50' rows='5' wrap='off' name='software'>"""
                for keyname in soft.keys():
                    if keyname != '':
                        html_form += '%s=%s\n' % (keyname, soft[keyname])
                html_form += '</textarea><br />'
    else:

        # loop and create textareas for each software entry

        if software_entries > 0:
            html_form += '<br /><b>Needed Software:</b><br />'

            software = rekeywords_dict['SOFTWARE']
            sublevel_required = []
            sublevel_optional = []

        if software.has_key('Sublevel') and software['Sublevel']:
            sublevel_required = software['Sublevel_required']
            sublevel_optional = software['Sublevel_optional']

        for _ in range(0, software_entries):
            html_form += """
<textarea cols='50' rows='5' wrap='off' name='software'>"""
            for sub_req in sublevel_required:
                html_form += '%s=   # required\n' % sub_req
            for sub_opt in sublevel_optional:
                html_form += '%s=   # optional\n' % sub_opt
            html_form += '</textarea><br />'
    if template and testprocedure_entry == 1:
        if template.has_key('TESTPROCEDURE'):
            html_form += """
<br /><b>Testprocedure</b> (in mRSL format):<br />
<textarea cols='50' rows='15' wrap='off' name='testprocedure'>"""

            base64string = ''
            for stringpart in template['TESTPROCEDURE']:
                base64string += stringpart
                decodedstring = base64.decodestring(base64string)
                html_form += decodedstring
            html_form += '</textarea>'
            output_objects.append({'object_type': 'html_form', 'text'
                                  : html_form})

            html_form = """
<br /><b>Expected .stdout file if testprocedure is executed</b><br />
<textarea cols='50' rows='10' wrap='off' name='verifystdout'>"""

            if template.has_key('VERIFYSTDOUT'):
                for line in template['VERIFYSTDOUT']:
                    html_form += line
            html_form += '</textarea>'

            html_form += """
<br /><b>Expected .stderr file if testprocedure is executed</b><br />
<textarea cols='50' rows='10' wrap='off' name='verifystderr'>"""
            if template.has_key('VERIFYSTDERR'):
                for line in template['VERIFYSTDERR']:
                    html_form += line
            html_form += '</textarea>'

            html_form += """
<br /><b>Expected .status file if testprocedure is executed</b><br />
<textarea cols='50' rows='10' wrap='off' name='verifystatus'>"""
            if template.has_key('VERIFYSTATUS'):
                for line in template['VERIFYSTATUS']:
                    html_form += line
            html_form += '</textarea>'
    elif testprocedure_entry == 1:

        html_form += """
<br /><b>Testprocedure</b> (in mRSL format):<br />
<textarea cols='50' rows='15' wrap='off' name='testprocedure'>"""

        html_form += \
            """::EXECUTE::
ls    
</textarea>
<br /><b>Expected .stdout file if testprocedure is executed</b><br />
<textarea cols='50' rows='10' wrap='off' name='verifystdout'></textarea>
<br /><b>Expected .stderr file if testprocedure is executed</b><br />
<textarea cols='50' rows='10' wrap='off' name='verifystderr'></textarea>
<br /><b>Expected .status file if testprocedure is executed</b><br />
<textarea cols='50' rows='10' wrap='off' name='verifystatus'></textarea>
"""

    environmentvariable = rekeywords_dict['ENVIRONMENTVARIABLE']
    sublevel_required = []
    sublevel_optional = []

    if environmentvariable.has_key('Sublevel')\
         and environmentvariable['Sublevel']:
        sublevel_required = environmentvariable['Sublevel_required']
        sublevel_optional = environmentvariable['Sublevel_optional']

    if template:
        if template.has_key('ENVIRONMENTVARIABLE'):
            env_list = template['ENVIRONMENTVARIABLE']

            if env_list:
                html_form += '<br /><b><br /><br /><b>Environments:</b><br />'
            for env in env_list:
                html_form += """
<textarea cols='50' rows='3' wrap='off' name='environment'>"""
                for keyname in env.keys():
                    if keyname != '':
                        html_form += '%s=%s\n' % (keyname, env[keyname])

                html_form += '</textarea>'
    else:

        if environment_entries > 0:
            html_form += '<br /><b><br /><br /><b>Environments:</b><br />'

        for _ in range(0, environment_entries):
            html_form += """
<textarea cols='50' rows='3' wrap='off' name='environment'>"""
            for sub_req in sublevel_required:
                html_form += '%s=   # required\n' % sub_req
            for sub_opt in sublevel_optional:
                html_form += '%s=   # optional\n' % sub_opt
            html_form += '</textarea><br />'

    html_form += """<br /><br /><input type='submit' value='Create' />
    </form>
"""
    output_objects.append({'object_type': 'html_form', 'text'
                          : html_form})
    return (output_objects, returnvalues.OK)


