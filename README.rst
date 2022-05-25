devpi-ldap: LDAP authentication for devpi-server
================================================

.. image:: https://img.shields.io/pypi/v/devpi-ldap.svg?style=flat
    :target: https://pypi.python.org/pypi/devpi-ldap/
    :alt: Latest Version

For use with devpi-server >= 2.1.0.

Installation
------------

``devpi-ldap`` needs to be installed alongside ``devpi-server``.

You can install it with::

    pip install devpi-ldap

For ``devpi-server`` there is no configuration needed to activate the plugin, as it will automatically discover the plugin through calling hooks using the setuptools entry points mechanism. However, you need to pass a path with a YAML config file to ``devpi-server``, via the ``--ldap-config`` command-line option.

Details about LDAP configuration below.

Configuration
-------------

A script named ``devpi-ldap`` can be used to test your LDAP configuration.

To configure LDAP, create a yaml file with a dictionary containing another dictionary under the ``devpi-ldap`` key with the following options:

``url``
  The url of the LDAP server.
  Using ``ldaps://`` enables SSL.
  No certificate validation is performed at the moment.

``tls``
  Parameters to the `ldap3.Tls object
  <http://ldap3.readthedocs.org/ssltls.html#the-tls-object>`_ for
  Transport Layer Security, used with LDAPS connections.

``server_pool``
  A list of LDAP pool servers. Either ``server_pool`` or ``url`` are mandatory, but they are mutually exclusive.
  A list entry itself is a dictionary containing a mandatory ``url`` item and optionally a ``tls`` item.

``user_template``
  The template to generate the distinguished name for the user.
  If the structure is fixed, this is faster than specifying a ``user_search``, but ``devpi-server`` can't know whether a user exists or not.

``user_search``
  If you can't or don't want to use ``user_template``, then these are the search settings for the users distinguished name.
  You can use ``username`` in the search filter.
  See specifics below.

``group_search``
  The search settings for the group objects of the user.
  You can use ``username`` and ``userdn`` (the distinguished name) in the search filter.
  See specifics below.

``referrals``
  Whether to follow referrals.
  This needs to be set to ``false`` in many cases when using LDAP via Active Directory on Windows.
  The default is ``true``.

``reject_as_unknown``
  Report all failed authentication attempts as ``unknown`` instead of
  ``reject``. This is useful e.g. if using the provided credentials to bind
  to ldap, in which case we cannot distinguish authentication failures from
  unknown users. ``unknown`` is required to let other auth hooks attempt to
  authenticate the user.

``timeout``
  The timeout for connections to the LDAP server. Defaults to 10 seconds.

  ``login_template``
  Template to insert the result from ``user_search`` into before attempting login

  ``group_required``
  Require the group search to be successful for authentication

The ``user_search`` and ``group_search`` settings are dictionaries with the following options:

``base``
  The base location from which to search.

``filter``
  The search filter.
  To use replacements, put them in curly braces.
  Example: ``(&(objectClass=group)(member={userdn}))``

``scope``
  The scope for the search.
  Valid values are ``base-object``, ``single-level`` and ``whole-subtree``.
  The default is ``whole-subtree``.

``attribute_name``
  The name of the attribute which contains the user DN which will be used to check the user's
  password. ``devpi-ldap`` will extract this attribute from the search results and attempt to
  bind to the LDAP server using this DN and the password supplied by the user. If this bind
  succeeds, access is granted.

``userdn``
  The distinguished name of the user which should be used for the search operation.
  For ``user_search``, if you don't have anonymous user search or for ``group_search`` if the users can't search their own groups, then you need to set this to a user which has the necessary rights.

``password``
  The password for the user in ``userdn``.

The YAML file should then look similar to this:

.. code-block:: yaml

    ---
    devpi-ldap:
      url: ldap://example.com
      user_template: CN={username},CN=Partition1,DC=Example,DC=COM
      group_search:
        base: CN=Partition1,DC=Example,DC=COM
        filter: (&(objectClass=group)(member={userdn}))
        attribute_name: CN

An example with user search and Active Directory might look like this:

.. code-block:: yaml

    ---
    devpi-ldap:
      url: ldap://example.com
      user_search:
        base: CN=Partition1,DC=Example,DC=COM
        filter: (&(objectClass=user)(sAMAccountName={username}))
        attribute_name: distinguishedName
      group_search:
        base: CN=Partition1,DC=Example,DC=COM
        filter: (&(objectClass=group)(member={userdn}))
        attribute_name: CN

With a server pool it might look like this:

.. code-block:: yaml

    ---
    devpi-ldap:
      server_pool:
        - url: ldap://server1.example.com:389
        - url: ldap://server2.example.com:3268
        - url: ldaps://server3.example.com:636
          tls:
            validate: 2 # ssl.CERT_REQUIRED
            ca_certs_file: /etc/ssl/certs/ca-certificates.crt
        - url: ldaps://server4.example.com:3269
          tls:
            validate: 2 # ssl.CERT_REQUIRED
            ca_certs_file: /etc/ssl/certs/ca-certificates.crt
      user_search:
        base: CN=Partition1,DC=Example,DC=COM
        filter: (&(objectClass=user)(sAMAccountName={username}))
        attribute_name: distinguishedName
      group_search:
        base: CN=Partition1,DC=Example,DC=COM
        filter: (&(objectClass=group)(member={userdn}))
        attribute_name: CN
