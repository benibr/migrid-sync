#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# --- BEGIN_HEADER ---
#
# ratelimits - grid daemon rate limit helper functions
# Copyright (C) 2010-2021  The MiG Project lead by Brian Vinter
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

"""MiG daemon rate limit functions"""

import os
import time
import traceback
from mig.shared.fileio import pickle, unpickle, acquire_file_lock, \
    release_file_lock, touch

default_max_user_hits, default_fail_cache = 5, 120
default_user_abuse_hits = 25
default_proto_abuse_hits = 25
default_max_secret_hits = 10

_rate_limits_filename = "rate_limits.pck"
_last_expired_filename = "last_expired"


def _acquire_rate_limits_lock(configuration, proto, exclusive=True):
    """Acquire rate limits lock for protocol proto"""

    flock_filepath = \
        os.path.join(configuration.mig_system_run,
                     "%s.%s.lock"
                     % (proto, _rate_limits_filename))

    flock = acquire_file_lock(flock_filepath, exclusive=exclusive)

    return flock


def _release_rate_limits_lock(lock):
    """Release rate limits lock"""
    return release_file_lock(lock)


def _load_rate_limits(configuration,
                      proto,
                      do_lock=True):
    """Load rate limits dict"""
    logger = configuration.logger
    rate_limits_filepath = os.path.join(configuration.mig_system_run,
                                        "%s.%s"
                                        % (proto, _rate_limits_filename))
    if do_lock:
        rate_limits_lock = _acquire_rate_limits_lock(
            configuration, proto, exclusive=False)
    # NOTE: file is typically on tmpfs so it may or may not exist at this point
    result = unpickle(rate_limits_filepath, logger, allow_missing=True)
    if do_lock:
        _release_rate_limits_lock(rate_limits_lock)

    if not isinstance(result, dict):
        logger.warning("failed to retrieve active %s rate limits from %s" % (
            proto, rate_limits_filepath))
        result = {}

    return result


def _save_rate_limits(configuration,
                      proto,
                      rate_limits,
                      do_lock=True):
    """Save rate limits dict"""
    logger = configuration.logger
    rate_limits_filepath = os.path.join(configuration.mig_system_run,
                                        "%s.%s"
                                        % (proto, _rate_limits_filename))
    if do_lock:
        rate_limits_lock = _acquire_rate_limits_lock(configuration, proto)
    result = pickle(rate_limits, rate_limits_filepath, logger)
    if do_lock:
        _release_rate_limits_lock(rate_limits_lock)

    if not result:
        logger.error("failed to save %s rate limits to %s" %
                     (proto, rate_limits_filepath))

    return result


def _get_last_expire(configuration, proto):
    """Get last expire timestamp"""
    last_expired_filepath = os.path.join(configuration.mig_system_run,
                                         "%s.%s"
                                         % (proto, _last_expired_filename))
    timestamp = 0
    if os.path.exists(last_expired_filepath):
        timestamp = os.path.getmtime(last_expired_filepath)

    return timestamp


def _set_last_expire(configuration, proto):
    """Set last expire timestamp"""
    last_expired_filepath = os.path.join(configuration.mig_system_run,
                                         "%s.%s"
                                         % (proto, _last_expired_filename))
    return touch(last_expired_filepath, configuration)


def hit_rate_limit(configuration, proto, client_address, client_id,
                   max_user_hits=default_max_user_hits):
    """Check if proto login from client_address with client_id should be
    filtered due to too many recently failed login attempts.
    The rate limit check lookup in rate limit cache.
    The rate limit cache is a set of nested dictionaries with
    client_address, protocol, client_id and secret as keys,
    the structure is shown in the 'update_rate_limit' doc-string.
    The rate limit cache maps the number of fails/hits for each
    IP, protocol, username and secret and helps distinguish e.g.
    any other users coming from the same gateway address.
    We always allow up to max_user_hits failed login attempts for a given username
    from a given address. This is in order to make it more difficult to
    effectively lock out another user with impersonating or random logins even
    from the same (gateway) address.

    NOTE: Use expire_rate_limit to remove old rate limit entries from the cache
    """
    logger = configuration.logger
    refuse = False

    _rate_limits = _load_rate_limits(configuration, proto)
    _address_limits = _rate_limits.get(client_address, {})
    _proto_limits = _address_limits.get(proto, {})
    _user_limits = _proto_limits.get(client_id, {})
    proto_hits = _proto_limits.get('hits', 0)
    user_hits = _user_limits.get('hits', 0)
    if user_hits >= max_user_hits:
        refuse = True

    if refuse:
        logger.warning("%s reached hit rate limit %d"
                       % (proto, max_user_hits)
                       + ", found %d of %d hit(s) "
                       % (user_hits, proto_hits)
                       + " for %s from %s"
                       % (client_id, client_address))

    return refuse


def update_rate_limit(configuration, proto, client_address, client_id,
                      login_success,
                      secret=None,
                      ):
    """Update rate limit database after proto login from client_address with
    client_id and boolean login_success status.
    The optional secret can be used to save the hash or similar so that
    repeated failures with the same credentials only count as one error.
    Otherwise some clients will retry on failure and hit the limit easily.
    The rate limit database is a set of nested dictionaries with
    client_address, protocol, client_id and secret as keys
    mapping the number of fails/hits for each IP, protocol, username and secret
    This helps distinguish e.g. any other users coming from the same
    gateway address.
    Example of rate limit database entry:
    {'127.0.0.1': {
        'fails': int (Total IP fails)
        'hits': int (Total IP fails)
        'sftp': {
            'fails': int (Total protocol fails)
            'hits': int (Total protocol hits)
            'user@some-domain.org: {
                'fails': int (Total user fails)
                'hits': int (Total user hits)
                'XXXYYYZZZ': {
                    'timestamp': float (Last updated)
                    'hits': int (Total secret hits)
                }
            }
        }
    }
    Returns tuple with updated hits:
    (address_hits, proto_hits, user_hits, secret_hits)
    """
    logger = configuration.logger
    status = {True: "success", False: "failure"}
    address_fails = old_address_fails = 0
    address_hits = old_address_hits = 0
    proto_fails = old_proto_fails = 0
    proto_hits = old_proto_hits = 0
    user_fails = old_user_fails = 0
    user_hits = old_user_hits = 0
    secret_hits = old_secret_hits = 0
    timestamp = time.time()
    if not secret:
        secret = timestamp

    rate_limits_lock = _acquire_rate_limits_lock(
        configuration, proto, exclusive=True)
    _rate_limits = _load_rate_limits(configuration, proto, do_lock=False)
    try:
        # logger.debug("update rate limit db: %s" % _rate_limits)
        _address_limits = _rate_limits.get(client_address, {})
        if not _address_limits:
            _rate_limits[client_address] = _address_limits
        _proto_limits = _address_limits.get(proto, {})
        if not _proto_limits:
            _address_limits[proto] = _proto_limits
        _user_limits = _proto_limits.get(client_id, {})

        address_fails = old_address_fails = _address_limits.get('fails', 0)
        address_hits = old_address_hits = _address_limits.get('hits', 0)
        proto_fails = old_proto_fails = _proto_limits.get('fails', 0)
        proto_hits = old_proto_hits = _proto_limits.get('hits', 0)
        user_fails = old_user_fails = _user_limits.get('fails', 0)
        user_hits = old_user_hits = _user_limits.get('hits', 0)
        if login_success:
            if _user_limits:
                address_fails -= user_fails
                address_hits -= user_hits
                proto_fails -= user_fails
                proto_hits -= user_hits
                user_fails = user_hits = 0
                del _proto_limits[client_id]
        else:
            if not _user_limits:
                _proto_limits[client_id] = _user_limits
            _secret_limits = _user_limits.get(secret, {})
            if not _secret_limits:
                _user_limits[secret] = _secret_limits
            secret_hits = old_secret_hits = _secret_limits.get('hits', 0)
            if secret_hits == 0:
                address_hits += 1
                proto_hits += 1
                user_hits += 1
            address_fails += 1
            proto_fails += 1
            user_fails += 1
            secret_hits += 1
            _secret_limits['timestamp'] = timestamp
            _secret_limits['hits'] = secret_hits
            _user_limits['fails'] = user_fails
            _user_limits['hits'] = user_hits
        _address_limits['fails'] = address_fails
        _address_limits['hits'] = address_hits
        _proto_limits['fails'] = proto_fails
        _proto_limits['hits'] = proto_hits
        if not _save_rate_limits(configuration,
                                 proto, _rate_limits, do_lock=False):
            raise IOError("%s save rate limits failed for %s" %
                          (proto, client_id))
    except Exception as exc:
        logger.error("update %s Rate limit failed: %s" % (proto, exc))
        logger.info(traceback.format_exc())

    _release_rate_limits_lock(rate_limits_lock)

    """
    logger.debug("update %s rate limit %s for %s\n"
                 % (proto, status[login_success], client_address)
                 + "old_address_fails: %d -> %d\n"
                 % (old_address_fails, address_fails)
                 + "old_address_hits: %d -> %d\n"
                 % (old_address_hits, address_hits)
                 + "old_proto_fails: %d -> %d\n"
                 % (old_proto_fails, proto_fails)
                 + "old_proto_hits: %d -> %d\n"
                 % (old_proto_hits, proto_hits)
                 + "old_user_fails: %d -> %d\n"
                 % (old_user_fails, user_fails)
                 + "old_user_hits: %d -> %d\n"
                 % (old_user_hits, user_hits)
                 + "secret_hits: %d -> %d\n"
                 % (old_secret_hits, secret_hits))
    """

    if user_hits != old_user_hits:
        logger.info("update %s rate limit" % proto
                    + " %s for %s" % (status[login_success], client_address)
                    + " from %d to %d hits" % (old_user_hits, user_hits))

    return (address_hits, proto_hits, user_hits, secret_hits)


def expire_rate_limit(configuration, proto,
                      fail_cache=default_fail_cache,
                      expire_delay=default_fail_cache):
    """Remove rate limit cache entries older than fail_cache seconds.
    Only entries in proto list will be touched,
    Returns:
    int (>=0): number of expired elements
    int (<0) number of seconds until to next expire based on on *expire_delay*
    """
    logger = configuration.logger
    now = time.time()
    address_fails = old_address_fails = 0
    address_hits = old_address_hits = 0
    proto_fails = old_proto_fails = 0
    proto_hits = old_proto_hits = 0
    user_fails = old_user_fails = 0
    user_hits = old_user_hits = 0
    expired = 0
    logger.debug("expire %r entries older than %d at %d with delay %d"
                 % (proto, fail_cache, now, expire_delay))
    check_expire = expire_delay \
        + _get_last_expire(configuration, proto)
    if check_expire > now:
        expired = round(now - check_expire)
        logger.debug("Postponed expire for %d seconds using %d seconds delay"
                     % (-expired, expire_delay))
        return expired

    rate_limits_lock = _acquire_rate_limits_lock(
        configuration, proto, exclusive=True)
    _rate_limits = _load_rate_limits(configuration, proto, do_lock=False)
    try:
        for _client_address in _rate_limits:
            # debug_msg = "expire addr: %s" % _client_address
            _address_limits = _rate_limits[_client_address]
            address_fails = old_address_fails = _address_limits['fails']
            address_hits = old_address_hits = _address_limits['hits']
            _proto_limits = _address_limits[proto]
            # debug_msg += ", proto: %s" % _proto
            proto_fails = old_proto_fails = _proto_limits['fails']
            proto_hits = old_proto_hits = _proto_limits['hits']
            # NOTE: iterate over a copy of proto limit keys to allow delete
            for _user in list(_proto_limits):
                if _user in ['hits', 'fails']:
                    continue
                # debug_msg += ", user: %s" % _user
                _user_limits = _proto_limits[_user]
                user_fails = old_user_fails = _user_limits['fails']
                user_hits = old_user_hits = _user_limits['hits']
                # NOTE: iterate over a copy of user limit keys to allow delete
                for _secret in list(_user_limits):
                    if _secret in ['hits', 'fails']:
                        continue
                    _secret_limits = _user_limits[_secret]
                    if _secret_limits['timestamp'] + fail_cache < now:
                        secret_hits = _secret_limits['hits']
                        # debug_msg += \
                        #"\ntimestamp: %s, secret_hits: %d" \
                        #    % (_secret_limits['timestamp'], secret_hits) \
                        #    + ", secret: %s" % _secret
                        address_fails -= secret_hits
                        address_hits -= 1
                        proto_fails -= secret_hits
                        proto_hits -= 1
                        user_fails -= secret_hits
                        user_hits -= 1
                        del _user_limits[_secret]
                        expired += 1
                _user_limits['fails'] = user_fails
                _user_limits['hits'] = user_hits
                # debug_msg += "\nold_user_fails: %d -> %d" \
                # % (old_user_fails, user_fails) \
                #    + "\nold_user_hits: %d -> %d" \
                #    % (old_user_hits, user_hits)
                if user_fails == 0:
                    # debug_msg += "\nRemoving expired user: %s" % _user
                    del _proto_limits[_user]
            _proto_limits['fails'] = proto_fails
            _proto_limits['hits'] = proto_hits
            # debug_msg += "\nold_proto_fails: %d -> %d" \
            # % (old_proto_fails, proto_fails) \
            #    + "\nold_proto_hits: %d -> %d" \
            #    % (old_proto_hits, proto_hits)
            _address_limits['fails'] = address_fails
            _address_limits['hits'] = address_hits
            # debug_msg += "\nold_address_fails: %d -> %d" \
            # % (old_address_fails, address_fails) \
            #    + "\nold_address_hits: %d -> %d" \
            #    % (old_address_hits, address_hits)
            # logger.debug(debug_msg)
        if not _save_rate_limits(configuration,
                                 proto, _rate_limits, do_lock=False):
            raise IOError("%s save rate limits failed" % proto)
    except Exception as exc:
        logger.error("expire rate limit failed: %s" % exc)
        logger.info(traceback.format_exc())

    _release_rate_limits_lock(rate_limits_lock)

    if expired:
        logger.info("expire %s rate limit expired %d items" % (proto,
                                                               expired))
        # logger.debug("expire %s rate limit expired %s" % (proto, expired))

    _set_last_expire(configuration, proto)

    """
    logger.debug("\nexpired %d %s rate limit(s)\n"
                 % (expired, proto)
                 + "address_fails: %d -> %d\n"
                 % (old_address_fails, address_fails)
                 + "address_hits: %d -> %d\n"
                 % (old_address_hits, address_hits)
                 + "proto_fails: %d -> %d\n"
                 % (old_proto_fails, proto_fails)
                 + "proto_hits: %d -> %d\n"
                 % (old_proto_hits, proto_hits)
                 + "user_fails: %d -> %d\n"
                 % (old_user_fails, user_fails)
                 + "user_hits: %d -> %d\n"
                 % (old_user_hits, user_hits))
    """

    return expired


def penalize_rate_limit(configuration, proto, client_address, client_id,
                        user_hits, max_user_hits=default_max_user_hits):
    """Stall client for a while based on the number of rate limit failures to
    make sure dictionary attackers don't really load the server with their
    repeated force-failed requests. The stall penalty is a linear function of
    the number of failed attempts.
    """
    logger = configuration.logger
    sleep_secs = 3 * (user_hits - max_user_hits)
    if sleep_secs > 0:
        logger.info("stall %s rate limited user %s from %s for %ds" %
                    (proto, client_id, client_address, sleep_secs))
        time.sleep(sleep_secs)
    return sleep_secs
