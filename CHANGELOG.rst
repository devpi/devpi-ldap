Changelog
=========

1.1.1 - 2016-01-28
------------------

- set minimum version of ldap3 library, which adds hiding of password in debug
  logging.
  [cannatag (Giovanni Cannata), rodcloutier (Rodrigue Cloutier), fschulze]

- change dependency for the ldap library, which was renamed.
  [kumy]

- fix issue #5: dn and distinguishedName may appear as a top level response
  attribute instead of the attributes list.
  [kainz (Bryon Roché)]

- fix issue #24: Ignore additional search result data.
  [bonzani (Patrizio Bonzani), fschulze]


1.1.0 - 2014-11-10
------------------

- add ``reject_as_unknown`` option
  [davidszotten (David Szotten)]


1.0.1 - 2014-10-10
------------------

- fix the plugin hook
  [fschulze]


1.0.0 - 2014-09-22
------------------

- initial release
  [fschulze (Florian Schulze)]
