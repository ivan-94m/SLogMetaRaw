# SPDX-License-Identifier: GPL-3.0-or-later
"""Guards for slogmetaraw/i18n.py: no window string may stay untranslated."""
import ast
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from slogmetaraw import i18n  # noqa: E402


def ui_t_strings():
    """All string literals passed to t() in ui.py."""
    src = open(os.path.join(ROOT, 'slogmetaraw', 'ui.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    out = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 't' and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            out.add(node.args[0].value)
    return out


class I18n(unittest.TestCase):
    def test_language_is_supported(self):
        self.assertIn(i18n.language(), i18n.LANGS)

    def test_unknown_strings_fall_back(self):
        self.assertEqual(i18n.t('stringa inesistente'), 'stringa inesistente')

    def test_window_strings_are_translated_everywhere(self):
        """Every t() string in ui.py must exist in en/es/pt/zh (it is the source)."""
        missing = {}
        for lang in ('en', 'es', 'pt', 'zh'):
            missing[lang] = sorted(s for s in ui_t_strings()
                                   if s not in i18n.TABLES[lang])
        self.assertEqual({k: v for k, v in missing.items() if v}, {},
                         'stringhe della finestra senza traduzione')

    def test_no_placeholders_are_lost(self):
        """Translation templates must keep the same %s/%d placeholders."""
        for lang, table in i18n.TABLES.items():
            for src, tr in table.items():
                if '%' in src:
                    self.assertEqual(re.findall(r'%[sd]', src), re.findall(r'%[sd]', tr),
                                     '%s: segnaposto diversi in %r -> %r' % (lang, src, tr))


if __name__ == '__main__':
    unittest.main()
