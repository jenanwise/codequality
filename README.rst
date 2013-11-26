codequality
===========

Simple code checking metatool.

codequality is glue around multiple external code checking tools. Its
goal is easy integration with editing environments and version control
(scm) tools.

Installation
------------

::

    sudo python setup.py install

Then, run:

::

    codequality --list-checkers

to see what checkers are available and installed on your machine. For
now, codequality only knows about a few checkers, and it will use any
that are available.

Usage details
-------------

See ``codequality --help``.

Some examples:

::

    codequality foo.py bar.js
    codequality --ignore "*junk/*"
    codequality --scm git
    codequality --scm git --rev HEAD~3

Integration
-----------

All output follows a simple parseable format:

::

    filename:linenumber:columnnumber: message

where the column number is optional (some external tools don't provide
it).

vim integration
~~~~~~~~~~~~~~~

::

    :setlocal makeprg=codequality\ %
    :make

see vim's ``:help make`` for details about how this works.

git post-commit integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Put the following in your ``.git/hooks/post-commit`` file:

::

    #!/bin/sh
    codequality --scm git -r HEAD

and make sure to ``chmod +x`` the post-commit hook file. You will then
have a codequality report after each local commit.
