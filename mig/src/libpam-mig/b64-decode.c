/**
 * Copyright 2010-2016 Comcast Cable Communications Management, LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 */
/*********************************************************************\

MODULE NAME:    b64.c

AUTHOR:         Bob Trower 08/04/01

PROJECT:        Crypt Data Packaging

DESCRIPTION:
                This little utility implements the Base64
                Content-Transfer-Encoding standard described in
                RFC1113 (http://www.faqs.org/rfcs/rfc1113.html).

                This is the coding scheme used by MIME to allow
                binary data to be transferred by SMTP mail.

                Groups of 3 bytes from a binary stream are coded as
                groups of 4 bytes in a text stream.

                The input stream is 'padded' with zeros to create
                an input that is an even multiple of 3.

                A special character ('=') is used to denote padding so
                that the stream can be decoded back to its exact size.

                Encoded output is formatted in lines which should
                be a maximum of 72 characters to conform to the
                specification.  This program defaults to 72 characters,
                but will allow more or less through the use of a
                switch.  The program enforces a minimum line size
                of 4 characters.

                Example encoding:

                The stream 'ABCD' is 32 bits long.  It is mapped as
                follows:

                ABCD

                 A (65)     B (66)     C (67)     D (68)   (None) (None)
                01000001   01000010   01000011   01000100

                16 (Q)  20 (U)  9 (J)   3 (D)    17 (R) 0 (A)  NA (=) NA (=)
                010000  010100  001001  000011   010001 000000 000000 000000

                QUJDRA==

                Decoding is the process in reverse.  A 'decode' lookup
                table has been created to avoid string scans.

DESIGN GOALS:   Specifically:
        Code is a stand-alone utility to perform base64
        encoding/decoding. It should be genuinely useful
        when the need arises and it meets a need that is
        likely to occur for some users.
        Code acts as sample code to show the author's
        design and coding style.

        Generally:
        This program is designed to survive:
        Everything you need is in a single source file.
        It compiles cleanly using a vanilla ANSI C compiler.
        It does its job correctly with a minimum of fuss.
        The code is not overly clever, not overly simplistic
        and not overly verbose.
        Access is 'cut and paste' from a web page.
        Terms of use are reasonable.

VALIDATION:     Non-trivial code is never without errors.  This
                file likely has some problems, since it has only
                been tested by the author.  It is expected with most
                source code that there is a period of 'burn-in' when
                problems are identified and corrected.  That being
                said, it is possible to have 'reasonably correct'
                code by following a regime of unit test that covers
                the most likely cases and regression testing prior
                to release.  This has been done with this code and
                it has a good probability of performing as expected.

                Unit Test Cases:

                case 0:empty file:
                    CASE0.DAT  ->  ->
                    (Zero length target file created
                    on both encode and decode.)

                case 1:One input character:
                    CASE1.DAT A -> QQ== -> A

                case 2:Two input characters:
                    CASE2.DAT AB -> QUJD -> AB

                case 3:Three input characters:
                    CASE3.DAT ABC -> QUJD -> ABC

                case 4:Four input characters:
                    case4.dat ABCD -> QUJDRA== -> ABCD

                case 5:All chars from 0 to ff, linesize set to 50:

                    AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIj
                    JCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZH
                    SElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWpr
                    bG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6P
                    kJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKz
                    tLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX
                    2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7
                    /P3+/w==

                case 6:Mime Block from e-mail:
                    (Data same as test case 5)

                case 7: Large files:
                    Tested 28 MB file in/out.

                case 8: Random Binary Integrity:
                    This binary program (b64.exe) was encoded to base64,
                    back to binary and then executed.

                case 9 Stress:
                    All files in a working directory encoded/decoded
                    and compared with file comparison utility to
                    ensure that multiple runs do not cause problems
                    such as exhausting file handles, tmp storage, etc.

                -------------

                Syntax, operation and failure:
                    All options/switches tested.  Performs as
                    expected.

                case 10:
                    No Args -- Shows Usage Screen
                    Return Code 1 (Invalid Syntax)
                case 11:
                    One Arg (invalid) -- Shows Usage Screen
                    Return Code 1 (Invalid Syntax)
                case 12:
                    One Arg Help (-?) -- Shows detailed Usage Screen.
                    Return Code 0 (Success -- help request is valid).
                case 13:
                    One Arg Help (-h) -- Shows detailed Usage Screen.
                    Return Code 0 (Success -- help request is valid).
                case 14:
                    One Arg (valid) -- Uses stdin/stdout (filter)
                    Return Code 0 (Sucess)
                case 15:
                    Two Args (invalid file) -- shows system error.
                    Return Code 2 (File Error)
                case 16:
                    Encode non-existent file -- shows system error.
                    Return Code 2 (File Error)
                case 17:
                    Out of disk space -- shows system error.
                    Return Code 3 (File I/O Error)

                -------------

                Compile/Regression test:
                    gcc compiled binary under Cygwin
                    Microsoft Visual Studio under Windows 2000
                    Microsoft Version 6.0 C under Windows 2000

DEPENDENCIES:   None

VERSION HISTORY:
                Bob Trower 08/04/01 -- Create Version 0.00.00B
                Trent Schmidt 2/7/2010 -- Modified code heavily for our use

\******************************************************************* */

#include "base64.h"

static void decodeblock(const uint8_t * in, uint8_t * out);
static size_t decode_core(const uint8_t * table, uint8_t start,
                          const uint8_t * input, const size_t input_size,
                          uint8_t * output);

/*
** decodeblock
**
** decode 4 '6-bit' characters into 3 8-bit binary bytes
*/
static void decodeblock(const uint8_t * in, uint8_t * out)
{
    out[0] = (uint8_t) (in[0] << 2 | in[1] >> 4);
    out[1] = (uint8_t) (in[1] << 4 | in[2] >> 2);
    out[2] = (uint8_t) (((in[2] << 6) & 0xc0) | in[3]);
}

size_t b64_get_decoded_buffer_size(const size_t encoded_size)
{
    size_t decoded_size;
    if ((0 == encoded_size)
        || (0 == encoded_size >> 2)) {
        return 0;
    }

    decoded_size = (encoded_size >> 2) * 3;
    return decoded_size;
}

/*
** decode
**
** decode a base64 encoded stream discarding padding, line breaks and noise
*/
size_t b64_decode(const uint8_t * input, const size_t input_size,
                  uint8_t * output)
{
    /*
     ** Translation Table to decode (created by author)
     */
    static const uint8_t cd64[] =
        "|$$$}rstuvwxyz{$$$$$$$>?@ABCDEFGHIJKLMNOPQRSTUVW$$$$$$XYZ[\\]^_`abcdefghijklmnopq";

    return decode_core(cd64, 43, input, input_size, output);
}

/*
** decode b64url
**
** decode a base64url encoded stream discarding padding, line breaks and noise
*/
size_t b64url_decode(const uint8_t * input, const size_t input_size,
                     uint8_t * output)
{
    /*
     ** Translation Table to decode (created by Weston Schmidt)
     */
    static const uint8_t cd64url[] =
        "|$$rstuvwxyz{$$$$$$$>?@ABCDEFGHIJKLMNOPQRSTUVW$$$$}$XYZ[\\]^_`abcdefghijklmnopq";

    return decode_core(cd64url, 45, input, input_size, output);
}

static size_t decode_core(const uint8_t * table, uint8_t start,
                          const uint8_t * input, const size_t input_size,
                          uint8_t * output)
{

    uint8_t in[4], v;
    uint8_t *out = output;
    int i, len;
    size_t count = 0;

    while (count < input_size) {
        for (len = 0, i = 0; (i < 4) && (count < input_size); i++) {
            v = 0;
            while ((count < input_size)
                   && (v == 0)) {
                v = input[count++];
                v = (uint8_t) ((v < start || v > 122) ? 0 : table[v - start]);
                if (v) {
                    v = (uint8_t) ((v == '$') ? 0 : v - 61);
                }
            }
            if (count < input_size || v != 0) {
                len++;
                if (v) {
                    in[i] = (uint8_t) (v - 1);
                }
            } else {
                in[i] = 0;
            }
        }
        if (len) {
            decodeblock(in, out);
            out += len - 1;
        }
    }
    return (out - output);
}
