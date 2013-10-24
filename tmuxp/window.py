# -*- coding: utf8 - *-
"""
    tmuxp.window
    ~~~~~~~~~~~~

    tmuxp helps you manage tmux workspaces.

    :copyright: Copyright 2013 Tony Narlock.
    :license: BSD, see LICENSE for details
"""
from __future__ import absolute_import, division, print_function, with_statement

import pipes
from .pane import Pane

from . import util, formats
import logging

logger = logging.getLogger(__name__)


class Window(util.TmuxMappingObject, util.TmuxRelationalObject):

    '''
    ``tmux(1) window``.
    '''

    childIdAttribute = 'pane_id'

    def __init__(self, session=None, **kwargs):

        if not session:
            raise ValueError('Window requires a Session, session=Session')

        self.session = session
        self.server = self.session.server

        if not 'window_id' in kwargs:
            raise ValueError('Window requires a `window_id`')

        self._window_id = kwargs['window_id']

        #self.server._update_windows()

    def __repr__(self):
        return "%s(%s %s:%s, %s)" % (
            self.__class__.__name__,
            self.get('window_id'),
            self.get('window_index'),
            self.get('window_name'),  # @todo, bug when window name blank
            self.session
        )

    @property
    def _TMUX(self, *args):

        attrs = {
            'window_id': self._window_id
        }

        # from https://github.com/serkanyersen/underscore.py
        def by(val, *args):
            for key, value in attrs.items():
                try:
                    if attrs[key] != val[key]:
                        return False
                except KeyError:
                    return False
                return True

        return list(filter(by, self.server._windows))[0]

    def tmux(self, *args, **kwargs):
        # if '-t' not in kwargs:
        #    kwargs['-t'] = self.get['session_id']
        return self.server.tmux(*args, **kwargs)

    def select_layout(self, layout=None):
        '''
        wrapper for ``tmux(1)``.

        .. code-block: bash

            $ tmux select-layout <layout>

        even-horizontal: Panes are spread out evenly from left to right across
        the window.

        even-vertical: Panes are spread evenly from top to bottom.

        main-horizontal: A large (main) pane is shown at the top of the window
        and the remaining panes are spread from left to right in the leftover
        space at the bottom.

        main-vertical: Similar to main-horizontal but the large pane is placed
        on the left and the others spread from top to bottom along the right.

        tiled: Panes are spread out as evenly as possible over the window in
        both rows and columns.

        custom: custom dimensions (see :term:`tmux(1)` manpages).

        :param layout: string of the layout, 'even-horizontal', 'tiled', etc.
        :type layout: string
        '''
        self.tmux(
            'select-layout',
            '-t%s' % self.target,      # target (name of session)
            layout
        )

    @property
    def target(self):
        return "%s:%s" % (self.session.get('session_id'), self.get('window_id'))

    def set_window_option(self, option, value):
        '''
        wrapper for ``tmux(1)``.

        .. code-block: bash

            $ tmux set-window-option <option> <value>

        :param value: window value. True/False will turn in 'on' and 'off'.
        :type value: string or bool
        '''

        if isinstance(value, bool) and value:
            value = 'on'
        elif isinstance(value, bool) and not value:
            value = 'off'

        process = self.tmux(
            'set-window-option',
            '-t%s' % self['window_id'],
            option, value
        )

        if process.stderr:
            if isinstance(process.stderr, list) and len(process.stderr) == int(1):
                process.stderr = process.stderr[0]
            raise ValueError(
                'tmux set-window-option stderr: %s' % process.stderr)

    def show_window_options(self, option=None):
        '''
        return a dict of options for the window.

        For familiarity with tmux, the option ``option`` param forwards to pick
        a single option, forwarding to :meth:`Window.show_window_option`.

        :param option: optional. show a single option.
        :type option: string
        :rtype: :py:obj:`dict`
        '''

        if option:
            return self.show_window_option(option)
        else:
            window_options = self.tmux(
                'show-window-options'
            ).stdout

        window_options = [tuple(item.split(' ')) for item in window_options]

        window_options = dict(window_options)

        for key, value in window_options.items():
            if value.isdigit():
                window_options[key] = int(value)

        return window_options

    def show_window_option(self, option):
        '''
        return a list of options for the window

        todo: test and return True/False for on/off string

        :param option: option to return.
        :type option: string
        :rtype: string, int
        '''

        window_option = self.tmux(
            'show-window-options', option
        ).stdout

        if window_option:
            window_option = [tuple(item.split(' '))
                             for item in window_option][0]
        else:
            return None

        if window_option[1].isdigit():
            window_option = (window_option[0], int(window_option[1]))

        return window_option[1]

    def rename_window(self, new_name):
        '''rename window and return new window object::

            $ tmux rename-window <new_name>

        :param new_name: name of the window
        :type new_name: string
        '''
        # new_name = pipes.quote(new_name)

        import shlex
        lex = shlex.shlex(new_name)
        lex.escape = ' '
        lex.whitespace_split = False
        # new_name = '\ '.join(new_name.split())

        try:
            self.tmux(
                'rename-window',
                '-t%s' % self.target,
                new_name
            )
            self['window_name'] = new_name
        except Exception as e:
            logger.error(e)

        self.server._update_windows()

        return self

    def select_pane(self, target_pane):
        '''
            ``$ tmux select-pane``

        :param target_pane: ``target_pane``, or ``-U``,``-D``, ``-L``, ``-R``.
        :type target_pane: string
        :rtype: :class:`Pane`

        Todo: make 'up', 'down', 'left', 'right' acceptable ``target_pane``.
        '''
        # if isinstance(target_pane, basestring) and not ':' not in target_pane or isinstance(target_pane, int):
        #    target_pane = "%s.%s" % (self.target, target_pane)

        proc = self.tmux('select-pane', '-t%s' % target_pane)

        if proc.stderr:
            raise Exception(proc.stderr)

        return self.attached_pane()

    def split_window(self, attach=True):
        '''
        Splits window. Returns the created :class:`Pane`.

        .. note::

            :term:`tmux(1)` will move window to the new pane if the
            ``split-window`` target is off screen. tmux handles the ``-d`` the
            same way as ``new-window`` and ``attach`` in
            :class:`Session.new_window`.

            By default, this will make the window the pane is created in
            active. To remain on the same window and split the pane in another
            target window, pass in ``attach=False``.


        Used for splitting window and holding in a python object.

        :param attach: make new window the current window after creating it,
                       default True.
        :param type: bool

        :rtype: :class:`Pane`
        '''

        pformats = ['session_name', 'session_id',
                    'window_index', 'window_id'] + formats.PANE_FORMATS
        tmux_formats = ['#{%s}\t' % f for f in pformats]

        #'-t%s' % self.attached_pane().get('pane_id'),
        # 2013-10-18 LOOK AT THIS, rm'd it..

        tmux_args = (
            '-t%s' % self.panes[0].get('pane_id'),
            '-P', '-F%s' % ''.join(tmux_formats),     # output
        )

        if not attach:
            tmux_args += ('-d',)

        pane = self.tmux(
            'split-window',
            *tmux_args
        )

        # tmux < 1.7. This is added in 1.7.
        if pane.stderr:
            raise Exception(pane.stderr)
            if 'pane too small' in pane.stderr:
                pass

            raise Exception(pane.stderr, self._TMUX, self.panes)
        else:
            pane = pane.stdout[0]

            pane = dict(zip(pformats, pane.split('\t')))

            # clear up empty dict
            pane = dict((k, v) for k, v in pane.items() if v)

        return Pane(window=self, **pane)

    def attached_pane(self):
        '''
        Return the attached :class:`Pane`.

        :rtype: :class:`Pane`
        '''
        for pane in self._panes:
            if 'pane_active' in pane:
                # for now pane_active is a unicode
                if pane.get('pane_active') == '1':
                    # return Pane(window=self, **pane)
                    return Pane(window=self, **pane)
                else:
                    continue

    def _list_panes(self):
        panes = self.server._update_panes()._panes

        panes = [
            p for p in panes if p['session_id'] == self.get('session_id')
        ]
        panes = [
            p for p in panes if p['window_id'] == self.get('window_id')
        ]
        return panes

    @property
    def _panes(self):
        return self._list_panes()

    def list_panes(self):
        '''Return list of :class:`Pane` for the window.

        :rtype: list of :class:`Pane`
        '''

        return [Pane(window=self, **pane) for pane in self._panes]

    @property
    def panes(self):
        return self.list_panes()
    children = panes
