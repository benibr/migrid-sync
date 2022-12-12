#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
#
# pwhash - helpers for password handling including for encryption and hashing
# Copyright (C) 2003-2022  The MiG Project lead by Brian Vinter
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
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.
#
# --- END_HEADER ---
#

"""Helpers for various password policy, crypt and hashing activities"""

from __future__ import print_function
from __future__ import absolute_import

from builtins import zip, range
from base64 import b64encode, b64decode, b16encode, b16decode, binascii, urlsafe_b64encode
from os import urandom
from random import SystemRandom
from string import ascii_lowercase, ascii_uppercase, digits
import hashlib

from mig.shared.base import force_utf8, force_native_str
from mig.shared.defaults import keyword_auto

try:
    import cracklib
except ImportError:
    # Optional cracklib not available - fail gracefully and check before use
    cracklib = None
try:
    import cryptography
    # NOTE: explicit submodule import is needed for Fernet use
    import cryptography.fernet
except ImportError:
    # Optional cryptography not available - fail gracefully and check before use
    cryptography = None

from mig.shared.defaults import POLICY_NONE, POLICY_WEAK, POLICY_MEDIUM, \
    POLICY_HIGH, POLICY_MODERN, POLICY_CUSTOM, PASSWORD_POLICIES

# Parameters to PBKDF2. Only affect new passwords.
SALT_LENGTH = 12
KEY_LENGTH = 24
HASH_FUNCTION = 'sha256'  # Must be in hashlib.
# Linear to the hashing time. Adjust to be high but take a reasonable
# amount of time on your server. Measure with:
# python -m timeit -s 'import passwords as p' 'p.make_hash("something")'
COST_FACTOR = 10000

# NOTE hook up available hashing algorithms once and for all
valid_hash_algos = {'md5': hashlib.md5}
for algo in hashlib.algorithms_guaranteed:
    valid_hash_algos[algo] = getattr(hashlib, algo)


def make_hash(password):
    """Generate a random salt and return a new hash for the password."""
    # NOTE: urandom already returns bytes as required for base64 encode
    salt = b64encode(urandom(SALT_LENGTH))
    # NOTE: hashlib functions require bytes, and post string format needs
    #       native strings to avoid actually inserting string type markers.
    return 'PBKDF2${}${}${}${}'.format(
        HASH_FUNCTION,
        COST_FACTOR,
        force_native_str(salt),
        force_native_str(b64encode(hashlib.pbkdf2_hmac(HASH_FUNCTION,
                                                       force_utf8(password),
                                                       salt, COST_FACTOR,
                                                       KEY_LENGTH))))


def check_hash(configuration, service, username, password, hashed,
               hash_cache=None, strict_policy=True, allow_legacy=False):
    """Check a password against an existing hash. First make sure the provided
    password satisfies the local password policy. The optional hash_cache
    dictionary argument can be used to cache recent lookups to save time in
    e.g. webdav where each operation triggers hash check.
    The optional boolean strict_policy argument decides whether or not the site
    password policy is enforced. It is used to disable checks for e.g.
    sharelinks where the policy is not guaranteed to apply.
    The optional boolean allow_legacy argument extends the strict_policy check
    so that passwords matching any configured password legacy policy are also
    accepted. Use only during active log in checks.
    """
    _logger = configuration.logger
    # NOTE: hashlib requires bytes
    pw_bytes = force_utf8(password)
    hash_bytes = force_utf8(hashed)
    pw_hash = make_simple_hash(password)
    if isinstance(hash_cache, dict) and \
            hash_cache.get(pw_hash, None) == hash_bytes:

        # _logger.debug("got cached hash: %s" % [hash_cache.get(pw_hash, None)])
        return True
    # We check policy AFTER cache lookup since it is already verified for those
    if strict_policy:
        try:
            assure_password_strength(configuration, password, allow_legacy)
        except Exception as exc:
            _logger.warning("%s password for %s does not fit local policy: %s"
                            % (service, username, exc))
            return False
    else:
        _logger.debug("password policy check disabled for %s login as %s" %
                      (service, username))
    # NOTE: we need native string format here for split
    hashed_str = force_native_str(hashed)
    algorithm, hash_function, cost_factor, salt, hash_a = hashed_str.split('$')
    assert algorithm == 'PBKDF2'
    hash_a = b64decode(hash_a)
    # NOTE: pbkdf2_hmac requires bytes for password and salt
    hash_b = hashlib.pbkdf2_hmac(hash_function, pw_bytes, force_utf8(salt),
                                 int(cost_factor), len(hash_a))
    assert len(hash_a) == len(hash_b)  # we requested this from pbkdf2_hmac()
    # Same as "return hash_a == hash_b" but takes a constant time.
    # See http://carlos.bueno.org/2011/10/timing.html
    diff = 0
    # NOTE: hashes are byte strings, but on python 3 iterating through them
    #       yields individual integer byte values directly vs individual char
    #       values on python 2. Apply ord() in the latter case for same result
    if isinstance(b'1'[0], int):
        byte_xlator = int
    else:
        byte_xlator = ord
    for char_a, char_b in zip(hash_a, hash_b):
        diff |= byte_xlator(char_a) ^ byte_xlator(char_b)
    match = (diff == 0)
    if isinstance(hash_cache, dict) and match:
        hash_cache[pw_hash] = hash_bytes
        # print("cached hash: %s" % hash_cache.get(pw_hash, None))
    return match


def scramble_digest(salt, digest):
    """Scramble digest for saving"""
    # NOTE: base64 encoders require bytes
    b16_digest = b16encode(force_utf8(digest))
    xor_int = int(salt, 16) ^ int(b16_digest, 16)
    # Python 2.6 fails to parse implicit positional args (-Jonas)
    # return '{:X}'.format(xor_int)
    return force_native_str('{0:X}'.format(xor_int))


def unscramble_digest(salt, digest):
    """Unscramble loaded digest"""
    xor_int = int(salt, 16) ^ int(digest, 16)
    # Python 2.6 fails to parse implicit positional args (-Jonas)
    # b16_digest = '{:X}'.format(xor_int)
    b16_digest = '{0:X}'.format(xor_int)
    return force_native_str(b16decode(b16_digest))


def make_digest(realm, username, password, salt):
    """Generate a digest for the credentials"""
    merged_creds = ':'.join([realm, username, password])
    # TODO: can we switch to proper md5 hexdigest without breaking webdavs?
    digest = 'DIGEST$custom$CONFSALT$%s' % scramble_digest(salt, merged_creds)
    return digest


def check_digest(configuration, service, realm, username, password, digest,
                 salt, digest_cache=None, strict_policy=True,
                 allow_legacy=False):
    """Check credentials against an existing digest. First make sure the
    provided password satisfies the local password policy. The optional
    digest_cache dictionary argument can be used to cache recent lookups to
    save time in e.g. webdav where each operation triggers digest check.
    The optional boolean strict_policy argument changes warnings about password
    policy incompliance to unconditional rejects.
    The optional boolean allow_legacy argument extends the strict_policy check
    so that passwords matching any configured password legacy policy are also
    accepted. Use only during active log in checks.
    """
    _logger = configuration.logger
    merged_creds = ':'.join([realm, username, password])
    creds_hash = make_simple_hash(merged_creds)
    if isinstance(digest_cache, dict) and \
            digest_cache.get(creds_hash, None) == digest:
        # print("got cached digest: %s" % digest_cache.get(creds_hash, None))
        return True
    # We check policy AFTER cache lookup since it is already verified for those
    try:
        assure_password_strength(configuration, password, allow_legacy)
    except Exception as exc:
        _logger.warning("%s password for %s does not fit local policy: %s"
                        % (service, username, exc))
        if strict_policy:
            return False
    # NOTE: we need to get cimputed bytes back to native format
    computed = force_native_str(make_digest(realm, username, password, salt))
    match = (computed == digest)
    if isinstance(digest_cache, dict) and match:
        digest_cache[creds_hash] = digest
        # print("cached digest: %s" % digest_cache.get(creds_hash, None))
    return match


def scramble_password(salt, password):
    """Scramble password for saving with fallback to base64 encoding if no salt
    is provided.
    """
    if not salt:
        return force_native_str(b64encode(password))
    xor_int = int(salt, 16) ^ int(b16encode(password), 16)
    return force_native_str('{0:X}'.format(xor_int))


def unscramble_password(salt, password):
    """Unscramble loaded password with fallback to base64 decoding if no salt
    is provided.
    """
    if not salt:
        try:
            unscrambled = b64decode(password)
        except binascii.Error:
            # Mimic legacy TypeError on py3 for consistency
            raise TypeError("Incorrect padding")
        return force_native_str(unscrambled)
    xor_int = int(salt, 16) ^ int(password, 16)
    b16_password = '{0:X}'.format(xor_int)
    return force_native_str(b16decode(b16_password))


def make_scramble(password, salt):
    """Generate a scrambled password"""
    return scramble_password(salt, password)


def check_scramble(configuration, service, username, password, scrambled,
                   salt=None, scramble_cache=None, strict_policy=True,
                   allow_legacy=False):
    """Make sure provided password satisfies local password policy and check
    match against existing scrambled password. The optional scramble_cache
    dictionary argument can be used to cache recent lookups to save time in
    e.g. openid where each operation triggers check.

    NOTE: we force strict password policy here since we may find weak legacy
    passwords in the user DB and they would easily give full account access.
    The optional boolean allow_legacy argument extends the strict_policy check
    so that passwords matching any configured password legacy policy are also
    accepted. Use only during active log in checks.
    """
    _logger = configuration.logger
    if isinstance(scramble_cache, dict) and \
            scramble_cache.get(password, None) == scrambled:
        # print("got cached scramble: %s" % scramble_cache.get(password, None))
        return True
    # We check policy AFTER cache lookup since it is already verified for those
    try:
        assure_password_strength(configuration, password, allow_legacy)
    except Exception as exc:
        _logger.warning('%s password for %s does not satisfy local policy: %s'
                        % (service, username, exc))
        if strict_policy:
            return False
    # NOTE: we need to get computed back from bytes to native string format
    computed = force_native_str(make_scramble(password, salt))
    match = (computed == scrambled)
    if isinstance(scramble_cache, dict) and match:
        scramble_cache[password] = scrambled
        # print("cached digest: %s" % scramble_cache.get(password, None))
    return match


def prepare_fernet_key(configuration, secret=keyword_auto):
    """Helper to extract and prepare a site-specific secret used for all
    Fernet symmetric encryption and decryption operations.
    """
    _logger = configuration.logger
    # NOTE: Fernet key must be 32 url-safe base64-encoded bytes
    fernet_key_bytes = 32
    if not secret:
        _logger.error('encrypt/decrypt requested without a secret')
        raise Exception('cannot encrypt/decrypt without a secret')
    if secret == keyword_auto:
        # NOTE: generate a static secret key based on configuration.
        # Use previously generated 'entropy' each time from a call to
        # cryptography.fernet.Fernet.generate_key()
        entropy = force_utf8('HyrqUFwxagFNcHANnDzVO-kMoU0ebo03pNaKHXce6xw=')
        # yet salt it with hash of a site-specific and non-public salt
        # to avoid disclosing salt or final key.
        if configuration.site_password_salt:
            #_logger.debug('making crypto key from pw salt and entropy')
            salt_data = configuration.site_password_salt
        elif configuration.site_digest_salt:
            #_logger.debug('making crypto key from digest salt and entropy')
            salt_data = configuration.site_digest_salt
        else:
            raise Exception('cannot encrypt/decrypt without a salt in conf')
        # NOTE: hashlib requires bytes
        salt_hash = hashlib.sha256(force_utf8(salt_data)).hexdigest()
        key_data = scramble_password(salt_hash, entropy)
    else:
        #_logger.debug('making crypto key from provided secret')
        key_data = secret
    key = force_native_str(urlsafe_b64encode(force_utf8(
        key_data[:fernet_key_bytes])))
    return key


def encrypt_password(configuration, password, secret=keyword_auto):
    """Encrypt password for saving"""
    _logger = configuration.logger
    _logger.debug('in encrypt_password')
    if cryptography:
        key = prepare_fernet_key(configuration, secret)
        password = force_utf8(password)
        fernet_helper = cryptography.fernet.Fernet(key)
        encrypted = fernet_helper.encrypt(password)
    else:
        _logger.error('encrypt requested without cryptography installed')
        raise Exception('cryptography requested in conf but not available')
    return encrypted


def decrypt_password(configuration, encrypted, secret=keyword_auto):
    """Decrypt encrypted password"""
    _logger = configuration.logger
    _logger.debug('in decrypt_password')
    if cryptography:
        key = prepare_fernet_key(configuration)
        encrypted = force_utf8(encrypted)
        fernet_helper = cryptography.fernet.Fernet(key)
        # Fernet takes byte token and returns bytes - force to native string
        password = force_native_str(fernet_helper.decrypt(encrypted))
    else:
        _logger.error('decrypt requested without cryptography installed')
        raise Exception('cryptography requested in conf but not available')
    return password


def make_encrypt(configuration, password, secret=keyword_auto):
    """Generate an encrypted password"""
    return encrypt_password(configuration, password, secret)


def check_encrypt(configuration, service, username, password, encrypted,
                  secret=keyword_auto, encrypt_cache=None, strict_policy=True,
                  allow_legacy=False):
    """Make sure provided password satisfies local password policy and check
    match against existing encrypted password. The optional encrypt_cache
    dictionary argument can be used to cache recent lookups to save time in
    repeated use cases.

    NOTE: we force strict password policy here since we may find weak legacy
    passwords in the user DB and they would easily give full account access.
    The optional boolean allow_legacy argument extends the strict_policy check
    so that passwords matching any configured password legacy policy are also
    accepted. Use only during active log in checks.
    """
    _logger = configuration.logger
    password = force_utf8(password)
    if isinstance(encrypt_cache, dict) and \
            encrypt_cache.get(password, None) == encrypted:
        # print("got cached encrypt: %s" % encrypt_cache.get(password, None))
        return True
    # We check policy AFTER cache lookup since it is already verified for those
    try:
        assure_password_strength(configuration, password, allow_legacy)
    except Exception as exc:
        _logger.warning('%s password for %s does not satisfy local policy: %s'
                        % (service, username, exc))
        if strict_policy:
            return False
    match = (make_encrypt(configuration, password, secret) == encrypted)
    if isinstance(encrypt_cache, dict) and match:
        encrypt_cache[password] = encrypted
        # print("cached digest: %s" % encrypt_cache.get(password, None))
    return match


def make_csrf_token(configuration, method, operation, client_id, limit=None):
    """Generate a Cross-Site Request Forgery (CSRF) token to help verify the
    authenticity of user requests. The optional limit argument can be used to
    e.g. put a timestamp into the mix, so that the token automatically expires.
    """
    salt = configuration.site_digest_salt
    merged = "%s:%s:%s:%s" % (method, operation, client_id, limit)
    # configuration.logger.debug("CSRF for %s" % merged)
    # NOTE: base64 enc and hashlib hash require bytes and return native string
    xor_id = "%s" % (int(salt, 16) ^ int(b16encode(force_utf8(merged)), 16))
    token = make_simple_hash(xor_id, 'sha256')
    return token


def make_csrf_trust_token(configuration, method, operation, args, client_id,
                          limit=None, skip_fields=[]):
    """A special version of the Cross-Site Request Forgery (CSRF) token used
    for cases where we already know the complete query arguments and just need
    to validate that they were passed untampered from us self.
    Packs the query args into the operation in a deterministic order by
    appending in sorted order from args.keys then just applies make_csrf_token.
    The optional skip_fields list can be used to exclude args from the token.
    That is mainly used to allow use for checking where the trust token is
    already part of the args and therefore should not be considered.
    """
    _logger = configuration.logger
    csrf_op = '%s' % operation
    if args:
        sorted_keys = sorted(list(args))
    else:
        sorted_keys = []
    for key in sorted_keys:
        if key in skip_fields:
            continue
        csrf_op += '_%s' % key
        for val in args[key]:
            csrf_op += '_%s' % val
    _logger.debug("made csrf_trust from url %s" % csrf_op)
    return make_csrf_token(configuration, method, csrf_op, client_id, limit)


def password_requirements(site_policy, logger=None):
    """Parse the custom password policy value to get the number of required
    characters and different character classes.
    """
    min_len, min_classes, errors = -1, 42, []
    if site_policy == POLICY_NONE:
        if logger:
            logger.debug('site password policy allows ANY password')
        min_len, min_classes = 0, 0
    elif site_policy == POLICY_WEAK:
        min_len, min_classes = 6, 2
    elif site_policy == POLICY_MEDIUM:
        min_len, min_classes = 8, 3
    elif site_policy == POLICY_HIGH:
        min_len, min_classes = 10, 4
    elif site_policy.startswith(POLICY_MODERN):
        try:
            _, min_len_str = site_policy.split(':', 1)
            min_len, min_classes = int(min_len_str), 1
        except Exception as exc:
            errors.append('modern password policy %s on invalid format: %s' %
                          (site_policy, exc))
    elif site_policy.startswith(POLICY_CUSTOM):
        try:
            _, min_len_str, min_classes_str = site_policy.split(':', 2)
            min_len, min_classes = int(min_len_str), int(min_classes_str)
        except Exception as exc:
            errors.append('custom password policy %s on invalid format: %s' %
                          (site_policy, exc))
    else:
        errors.append('unknown password policy keyword: %s' % site_policy)
    if logger:
        logger.debug('password policy %s requires %d chars from %d classes' %
                     (site_policy, min_len, min_classes))
    return min_len, min_classes, errors


def parse_password_policy(configuration, use_legacy=False):
    """Parse the custom password policy in configuration to get the number of
    required characters and different character classes.
    NOTE: fails hard later if invalid policy is used for best security.
    The optional boolean use_legacy argument results in any configured
    password legacy policy being used instead of the default password policy.
    """
    _logger = configuration.logger
    if use_legacy:
        policy = configuration.site_password_legacy_policy
    else:
        policy = configuration.site_password_policy
    min_len, min_classes, errors = password_requirements(policy, _logger)
    for err in errors:
        _logger.error(err)
    return min_len, min_classes


def __assure_password_strength_helper(configuration, password, use_legacy=False):
    """Helper to check if password fits site password policy or password legacy
    policy in terms of length and required number of different character classes.
    We split into four classes for now, lowercase, uppercase, digits and other.
    The optional use_legacy argument is used to decide if the configured normal
    password policy or any configured password legacy policy should apply.
    """
    _logger = configuration.logger
    if use_legacy:
        policy_fail_msg = 'password does not fit password legacy policy'
    else:
        policy_fail_msg = 'password does not fit password policy'
    min_len, min_classes = parse_password_policy(configuration, use_legacy)
    if min_len < 0 or min_classes > 4:
        raise Exception('parse password policy failed: %d %d (use_legacy: %s)'
                        % (min_len, min_classes, use_legacy))
    if len(password) < min_len:
        raise ValueError('%s: password too short, at least %d chars required' %
                         (policy_fail_msg, min_len))
    char_class_map = {'lower': ascii_lowercase, 'upper': ascii_uppercase,
                      'digits': digits}
    base_chars = ''.join(list(char_class_map.values()))
    pw_classes = []
    for i in password:
        if i not in base_chars and 'other' not in pw_classes:
            pw_classes.append('other')
            continue
        for (char_class, values) in char_class_map.items():
            if i in "%s" % values and not char_class in pw_classes:
                pw_classes.append(char_class)
                break
    if len(pw_classes) < min_classes:
        raise ValueError('%s: password too simple, >= %d char classes required' %
                         (policy_fail_msg, min_classes))
    if configuration.site_password_cracklib:
        if cracklib:
            # NOTE: min_len does not exactly match cracklib.MIN_LENGTH meaning
            #       but we just make sure cracklib does not directly increase
            #       policy requirements.
            cracklib.MIN_LENGTH = min_len + min_classes
            try:
                # NOTE: this raises ValueError if password is too simple
                cracklib.VeryFascistCheck(password)
            except Exception as exc:
                raise ValueError("cracklib refused password: %s" % exc)
        else:
            raise Exception('cracklib requested in conf but not available')
    return True


def assure_password_strength(configuration, password, allow_legacy=False):
    """Make sure password fits site password policy in terms of length and
    required number of different character classes.
    We split into four classes for now, lowercase, uppercase, digits and other.
    The optional allow_legacy argument should be supplied for calls where any
    configured password legacy policy should apply. Namely for cases where only
    an actual password log in is checked, but not when saving a new password
    anywhere.
    """
    _logger = configuration.logger
    site_policy = configuration.site_password_policy
    site_legacy_policy = configuration.site_password_legacy_policy
    try:
        __assure_password_strength_helper(configuration, password, False)
        _logger.debug('password compliant with password policy (%s)' %
                      site_policy)
        return True
    except ValueError as err:
        if site_legacy_policy and allow_legacy:
            _logger.info("%s. Proceed with legacy policy check." % err)
        else:
            _logger.warning("%s" % err)
            raise err

    try:
        __assure_password_strength_helper(configuration, password, True)
        _logger.debug('password compliant with password legacy policy (%s)' %
                      site_legacy_policy)
        return True
    except ValueError as err:
        _logger.warning("%s" % err)
        raise err


def valid_login_password(configuration, password):
    """Helper to verify that provided password is valid for login purposes.
    This is a convenience wrapper for assure_password_strength to get a boolean
    result. Used in grid_webdavs and from sftpsubsys PAM helper.
    """
    _logger = configuration.logger
    try:
        assure_password_strength(configuration, password, allow_legacy=True)
        return True
    except ValueError as err:
        return False
    except Exception as exc:
        _logger.error("unexpected exception in valid_login_password: %s" % exc)
        return False


def make_simple_hash(val, algo='md5'):
    """Generate a simple hash for val and return the N character hexdigest.
    By default the hash algorithm is md5 with 32-char hash, but other hashlib
    algorithms are supported as well.
    """
    # NOTE: hashlib functions require bytes and hexdigest returns native string
    if not algo in valid_hash_algos:
        algo = 'md5'
    hash_helper = valid_hash_algos[algo]
    return hash_helper(force_utf8(val)).hexdigest()


def make_path_hash(configuration, path):
    """Generate a 128-bit md5 hash for path and return the 32 char hexdigest.
    Used to compress long paths into a fixed length string ID without
    introducing serious collision risks, under the assumption that the
    total number of path hashes is say in the millions or less. Please refer
    to the collision risk calculations at e.g
    http://preshing.com/20110504/hash-collision-probabilities/
    https://en.wikipedia.org/wiki/Birthday_attack
    for the details.
    """
    _logger = configuration.logger
    _logger.debug("make path hash for %s" % path)
    return make_simple_hash(path)


def generate_random_ascii(count, charset):
    """Generate a string of count random characters from given charset"""
    return ''.join(SystemRandom().choice(charset) for _ in range(count))


def generate_random_password(configuration, tries=42):
    """Generate a password string of random characters from allowed password
    charset and taking any active password policy in configuration into
    account.
    Tries can be used to tune the number of attempts to make sure random
    selection does not yield too weak a password.
    """
    _logger = configuration.logger
    count, classes = parse_password_policy(configuration)
    # TODO: use the password charset from safeinput instead?
    charset = ascii_lowercase
    if classes > 1:
        charset += ascii_uppercase
    if classes > 2:
        charset += digits
    if classes > 3:
        charset += ',.;:+=&%#@£$/?*'
    for i in range(tries):
        _logger.debug("make password with %d chars from %s" % (count, charset))
        password = generate_random_ascii(count, charset)
        try:
            assure_password_strength(configuration, password)
            return password
        except ValueError as err:
            _logger.warning("generated password %s didn't fit policy - retry"
                            % password)
            pass
    _logger.error("failed to generate password to fit site policy")
    raise ValueError("Failed to generate suitable password!")


if __name__ == "__main__":
    from mig.shared.conf import get_configuration_object
    configuration = get_configuration_object()
    for policy in PASSWORD_POLICIES:
        if policy == POLICY_MODERN:
            policy += ':12'
        elif policy == POLICY_CUSTOM:
            policy += ':12:4'
        configuration.site_password_policy = policy
        for pw in ('', 'abc', 'dbey3h', 'abcdefgh', '12345678', 'test1234',
                   'password', 'djeudmdj', 'Password12', 'P4s5W0rd',
                   'GoofBall', 'b43kdn22', 'Dr3Ab3_2', 'kasd#D2s',
                   'fsk34dsa-.32d', 'd3kk3mdkkded', 'Loh/p4iv,ahk',
                   'MinimumIntrusionGrid', 'correcthorsebatterystaple'):
            try:
                res = assure_password_strength(configuration, pw)
            except Exception as exc:
                res = "False (%s)" % exc
            print("Password %r follows %s password policy: %s" %
                  (pw, policy, res))

            try:
                # print("Encrypt password %r" % pw)
                encrypted = encrypt_password(configuration, pw)
                # print("Decrypt encrypted password %r" % encrypted)
                decrypted = decrypt_password(configuration, encrypted)
                # print("Password %r encrypted to %s and decrypted to %s ." %
                #      (pw, encrypted, decrypted))
                if pw != decrypted:
                    raise ValueError("Password enc+dec corruption: %r vs %r" %
                                     (pw, decrypted))
                print("Password %r encrypted and decrypted correctly" % pw)
            except Exception as exc:
                print("Failed to handle encrypt/decrypt %s : %s" % (pw, exc))
                # import traceback
                # print(traceback.format_exc())
