#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
# textarea - [insert a few words of module description on this line]
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

# Minimum Intrusion Grid

"""
This is the form handler called by html pages
@todo detect and notify user if a filenumber is used twice
@todo better user input validation
"""

import cgi
import os
import time

# TODO: is xmlrpclib used at all?

import xmlrpclib
import base64

import shared.returnvalues as returnvalues
import shared.mrslkeywords as mrslkeywords
from shared.functional import validate_input_and_cert, REJECT_UNSET
from shared.init import initialize_main_variables
from shared.upload import handle_package_upload
from shared.fileio import write_file
from shared.job import new_job
from shared.validstring import valid_user_path


def signature():
    defaults = {}
    return ['todo: signature', defaults]


def convert_control_value_to_line(form_key, user_arguments_dict):
    """convert to line to be used in file """

    value = user_arguments_dict[form_key][0].strip()
    return value


def strip_dir(path):
    """Strip directory part of path for all known path formats. We can
    not simply use os.path.basename() as it doesn't work if client
    supplies, say, an absolute windows path.
    """

    if path.find(':') >= 0:

        # Windows absolute path - name is just right of rightmost backslash

        index = path.rfind('\\')
        name = path[index + 1:]
    else:
        name = os.path.basename(path)
    return name


def handle_form_input(filenumber, user_arguments_dict, configuration):
    """Get keyword_FILENUMBER_X_Y from form and put it in mRSL format
    or write plain file
    """

    file_type = ''

    output = ''
    keys = mrslkeywords.get_keywords_dict(configuration).keys()

    # FILE keyword used to indicate a plain file should be created

    keys.append('PLAINFILE')
    keys.append('FILEUPLOAD')
    for keyword in keys:
        counter_1 = -1
        counter_2 = 0
        end_with_newline = False

        while True:
            form_key = '%s_%s_%s_%s' % (keyword.lower(), filenumber,
                    counter_1, counter_2 + 1)
            form_key_line = '%s_%s_%s_%s' % (keyword.lower(),
                    filenumber, counter_1 + 1, counter_2)

            if user_arguments_dict.has_key(form_key):

                # Y increased, append value

                output += convert_control_value_to_line(form_key,
                        user_arguments_dict)
                counter_2 += 1
            elif user_arguments_dict.has_key(form_key_line):

                # X increased. If 0_0 write keyword. Write new line.

                if counter_1 == -1 and counter_2 == 0:
                    if keyword == 'PLAINFILE':
                        file_type = 'plain'
                    if keyword == 'FILEUPLOAD':
                        file_type = 'fileupload'
                    else:

                        # write keyword the first time only

                        output += '::%s::\n' % keyword
                        end_with_newline = True

                output += '%s\n'\
                     % convert_control_value_to_line(form_key_line,
                        user_arguments_dict)
                counter_1 += 1
                counter_2 = 0
            else:

                # X+1 or Y+1 not found, append newline if requested

                if end_with_newline:
                    output += '\n'
                break

    return (output, file_type)


def main(cert_name_no_spaces, user_arguments_dict):
    """Main function used by front end"""

    (configuration, logger, output_objects, op_name) = \
        initialize_main_variables(op_title=True, op_header=False)
    output_objects.append({'object_type': 'header', 'text'
                          : 'MiG submit job/file'})

    uploaddir = configuration.user_home + cert_name_no_spaces + os.sep
    submitstatuslist = []
    fileuploadobjs = []
    filenumber = 0

    # Please note that base_dir must end in slash to avoid access to
    # other user dirs when own name is a prefix of another user name

    base_dir = os.path.abspath(configuration.user_home + os.sep
                                + cert_name_no_spaces) + os.sep

    while True:
        (content, file_type) = handle_form_input(filenumber,
                user_arguments_dict, configuration)

        if not content:

            # no data for filenumber found

            break

        # always append mrsltextarea if available!

        try:
            content += user_arguments_dict['mrsltextarea_%s'
                     % filenumber][0]
        except:
            pass
        content += '\n'

        mrslfiles_to_parse = []
        submit_mrslfiles = False
        submitmrsl_key = 'submitmrsl_%s' % filenumber
        if user_arguments_dict.has_key(submitmrsl_key):
            val = str(user_arguments_dict[submitmrsl_key][0]).upper()
            if val == 'ON' or val == 'TRUE':
                submit_mrslfiles = True
        fileuploadobj = {'object_type': 'fileuploadobj',
                         'submitmrsl': submit_mrslfiles}

        if file_type == 'plain':

            # get filename

            filename_key = 'FILENAME_%s' % filenumber
            if not user_arguments_dict.has_key(filename_key):
                output_objects.append({'object_type': 'error_text',
                        'text'
                        : "The specified file_type is 'plain', but a filename value was not found. The missing control should be named %s"
                         % filename_key})
                return (output_objects, returnvalues.CLIENT_ERROR)

            local_filename = uploaddir\
                 + convert_control_value_to_line(filename_key)

            if not valid_user_path(local_filename, base_dir):
                output_objects.append({'object_type': 'error_text',
                        'text'
                        : 'Are you trying to circumvent permissions on the file system? Do not use .. in the path string!'
                        })
                return (output_objects, returnvalues.CLIENT_ERROR)

            # A new filename was created, write content to file

            if not write_file(content, local_filename, logger):
                output_objects.append({'object_type': 'error_text',
                        'text': 'Could not write: %s' % local_filename})
                return (output_objects, returnvalues.SYSTEM_ERROR)
            fileuploadobj['saved'] = True

            # msg += "%s created!" % local_filename

            fileuploadobj['name'] = os.sep\
                 + convert_control_value_to_line(filename_key)

            if local_filename.upper().endswith('.MRSL')\
                 and submit_mrslfiles:
                mrslfiles_to_parse.append[local_filename]
        elif file_type == 'fileupload':

            # An input type=file was found

            extract_packages = False
            extract_key = 'extract_%s' % filenumber
            if user_arguments_dict.has_key(extract_key):
                val = str(user_arguments_dict[extract_key][0]).upper()
                if val == 'ON' or val == 'TRUE':
                    extract_packages = True
            fileupload_key = 'fileupload_%s_0_0' % filenumber

            # if not fileitem.filename:

            if not user_arguments_dict.has_key(fileupload_key
                     + 'filename'):
                output_objects.append({'object_type': 'error_text',
                        'text': 'NO FILENAME error'})
                return (output_objects, returnvalues.CLIENT_ERROR)

            remote_filename = ''
            default_remotefilename_key = 'default_remotefilename_%s'\
                 % filenumber
            if user_arguments_dict.has_key(default_remotefilename_key):
                fileuploadobjs.append(fileuploadobj)
                remote_filename = \
                    user_arguments_dict[default_remotefilename_key][0]

            # remotefilename overwrites default_remotefilename if it exists

            remotefilename_key = 'remotefilename_%s' % filenumber
            if user_arguments_dict.has_key(remotefilename_key):
                remote_filename = \
                    user_arguments_dict[remotefilename_key][0]

            base_name = strip_dir(user_arguments_dict[fileupload_key
                                   + 'filename'])

            # print "fileitem: %s" % fileitem

            if not remote_filename:
                remote_filename = base_name

            # if remote_filename is a directory, use client's local filename
            # for the last part of the filename

            if remote_filename.strip().endswith(os.sep):
                remote_filename += base_name

            # else:
                # remote_filename = fileitem.filename

            # if not fileitem.file:

            if not user_arguments_dict.has_key(fileupload_key):
                output_objects.append({'object_type': 'error_text',
                        'text': 'File content not found!'})
                return (output_objects, returnvalues.CLIENT_ERROR)

            local_filename = os.path.abspath(base_dir + remote_filename)
            if not valid_user_path(local_filename, base_dir):
                output_objects.append({'object_type': 'error_text',
                        'text'
                        : 'Are you trying to circumvent permissions on the file system? Do not use .. in the path string! This event has been logged! %s'
                         % cert_name_no_spaces})
                return (output_objects, returnvalues.CLIENT_ERROR)

            if not os.path.isdir(os.path.dirname(local_filename)):
                try:
                    os.makedirs(os.path.dirname(local_filename), 0777)
                except Exception, e:
                    fileuploadobj['message'] = \
                        {'object_type': 'error_text',
                         'text': 'Exception creating dirs %s'\
                          % os.path.dirname(local_filename)}
            fileuploadobj['name'] = remote_filename

            # reads uploaded file into memory

            binary = user_arguments_dict.has_key('%s_is_encoded'
                     % fileupload_key)
            if binary:
                data = user_arguments_dict[fileupload_key][-1]
                data = str(base64.decodestring(data))
            else:
                data = user_arguments_dict[fileupload_key][-1]

            # write file in memory to disk

            if not write_file(data, local_filename,
                              configuration.logger):
                output_objects.append({'object_type': 'error_text',
                        'text': 'Error writing file in memory to disk'})
                return (output_objects, returnvalues.SYSTEM_ERROR)
            fileuploadobj['saved'] = True

            # Tell the client about the current settings (extract and submit)
            # extract_str = "Extract files from packages (.zip, .tar.gz, .tgz, .tar.bz2): "
            # if extract_packages:
            #    extract_str += "ON"
            # else:
            #    extract_str += "OFF"
            # output_objects.append({"object_type":"text", "text":extract_str})

            fileuploadobj['extract_packages'] = extract_packages

            # submit_str = "Submit mRSL files to parser (including .mRSL files in packages!): "
            # if submit_mrslfiles:
            #    submit_str += "ON"
            # else:
            #    submit_str += "OFF"
            # output_objects.append({"object_type":"text", "text":submit_str})

            # handle file package

            if extract_packages\
                 and (local_filename.upper().endswith('.ZIP')
                       or local_filename.upper().endswith('.TAR.GZ')
                       or local_filename.upper().endswith('.TGZ')
                       or local_filename.upper().endswith('.TAR.BZ2')):
                (status, msg) = handle_package_upload(local_filename,
                        remote_filename, cert_name_no_spaces,
                        configuration, submit_mrslfiles)
                if not status:
                    output_objects.append({'object_type': 'error_text',
                            'text': 'Error: %s' % msg})
                    return (output_objects, returnvalues.CLIENT_ERROR)
                submitstatuslist = msg
            else:

                # output_objects.append({"object_type":"text", "text":msg})
                # a "normal" (non-package) file was uploaded

                try:
                    output_objects.append({'object_type': 'text', 'text'
                            : 'File saved: %s' % remote_filename})
                except Exception, e:
                    output_objects.append({'object_type': 'error_text',
                            'text'
                            : 'File seems to be saved, but could not get file size %s'
                             % e})
                    return (output_objects, returnvalues.SYSTEM_ERROR)
            fileuploadobj['size'] = os.path.getsize(local_filename)
            fileuploadobj['name'] = remote_filename

            # Check if the extension is .mRSL

            if local_filename.upper().endswith('.MRSL')\
                 and submit_mrslfiles:

                # A .mrsl file was uploaded!
                # output_objects.append({"object_type":"text", "text":"File name on MiG server: %s" % (remote_filename)})

                mrslfiles_to_parse.append(local_filename)
        else:

            # mrsl file created by html controls. create filename. Loop until a filename that do not exits is created

            html_generated_mrsl_dir = uploaddir + 'html_generated_mrsl'
            if os.path.exists(html_generated_mrsl_dir)\
                 and not os.path.isdir(html_generated_mrsl_dir):

                # oops, user might have created a file with the same name

                output_objects.append({'object_type': 'error_text',
                        'text'
                        : 'Please make sure %s does not exist or is a directory!'
                         % 'html_generated_mrsl/'})
                return (output_objects, returnvalues.CLIENT_ERROR)
            if not os.path.isdir(html_generated_mrsl_dir):
                os.mkdir(html_generated_mrsl_dir)
            while True:
                time_c = time.gmtime()
                timestamp = '%s_%s_%s__%s_%s_%s' % (
                    time_c[1],
                    time_c[2],
                    time_c[0],
                    time_c[3],
                    time_c[4],
                    time_c[5],
                    )
                local_filename = html_generated_mrsl_dir\
                     + '/TextAreaAt_' + timestamp + '.mRSL'
                if not os.path.isfile(local_filename):
                    break

            # A new filename was created, write content to file

            if not write_file(content, local_filename, logger):
                output_objects.append({'object_type': 'error_text',
                        'text': 'Could not write: %s' % local_filename})
                return (output_objects, returnvalues.SYSTEM_ERROR)
            fileuploadobj['name'] = os.sep\
                 + 'html_generated_mrsl/TextAreaAt_' + timestamp\
                 + '.mRSL'
            fileuploadobj['size'] = os.path.getsize(local_filename)
            mrslfiles_to_parse.append(local_filename)
        fileuploadobjs.append(fileuploadobj)

        # Submit selected file(s)

        for mrslfile in mrslfiles_to_parse:

            # do not reveal full path of mrsl file to client

            relative_filename = os.sep + mrslfile.replace(uploaddir, '')
            submitstatus = {'object_type': 'submitstatus',
                            'name': relative_filename}

            (status, newmsg, job_id) = new_job(mrslfile,
                    cert_name_no_spaces, configuration, False, True)
            if not status:

                # output_objects.append({"object_type":"error_text", "text":"%s" % newmsg})

                submitstatus['status'] = False
                submitstatus['message'] = newmsg
            else:

                # return (output_objects, returnvalues.CLIENT_ERROR)

                submitstatus['status'] = True
                submitstatus['job_id'] = job_id

                # output_objects.append({"object_type":"text", "text":"%s" % newmsg})

            submitstatuslist.append(submitstatus)

        # prepare next loop

        filenumber += 1
    output_objects.append({'object_type': 'header', 'text'
                          : 'Uploaded/created files'})
    output_objects.append({'object_type': 'fileuploadobjs',
                          'fileuploadobjs': fileuploadobjs})
    output_objects.append({'object_type': 'header', 'text'
                          : 'Submitted jobs'})
    output_objects.append({'object_type': 'submitstatuslist',
                          'submitstatuslist': submitstatuslist})

    # output_objects.append({"object_type":"text","text":str(submitstatuslist) + " *** " + str(mrslfiles_to_parse)})

    return (output_objects, returnvalues.OK)


