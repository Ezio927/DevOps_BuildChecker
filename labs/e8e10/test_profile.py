import json, tempfile, unittest
from pathlib import Path
from lab import fixture,scan,patch,commit

class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)/'sample';fixture(self.p)

    def test_independent_known_edges(self):
        r=scan(self.p)
        self.assertEqual(r['actual']['main.o'],['config.h','main.c'])
        self.assertEqual({(f['type'],f['dependency']) for f in r['findings']},{('MISSING','config.h'),('REDUNDANT','unused.h')})

    def test_unchanged_reuses_both_targets(self):
        r=scan(self.p,scan(self.p));self.assertEqual(r['reused'],['main.o','helper.o']);self.assertEqual(r['refreshed'],[])

    def test_include_added_invalidates_cache(self):
        old=scan(self.p)
        (self.p/'main.c').write_text('#include "extra.h"\n'+(self.p/'main.c').read_text());commit(self.p,'new include')
        r=scan(self.p,old)
        self.assertIn(['MISSING','main.o','extra.h'],r['added']);self.assertEqual(len(r['refreshed']),2)

    def test_continued_include_macro_uses_new_header(self):
        source = self.p / 'main.c'
        source.write_text('#define CHOSEN \\\n"config.h"\n#include CHOSEN\n')
        old = scan(self.p)
        source.write_text(source.read_text().replace('"config.h"', '"extra.h"'))
        self.assertEqual(scan(self.p, old)['actual']['main.o'], ['extra.h', 'main.c'])

    def test_block_comment_can_hide_a_directive(self):
        source = self.p / 'main.c'
        source.write_text('/* comment */\n#include "config.h"\n// */\n')
        old = scan(self.p)
        source.write_text(source.read_text().replace('/* comment */', '/* comment'))
        self.assertEqual(scan(self.p, old)['actual']['main.o'], ['main.c'])

    def test_unindexed_header_is_rechecked_for_its_own_target(self):
        (self.p / 'main.c').write_text('#include "list.inc"\n')
        header = self.p / 'list.inc'
        header.write_text('#include "config.h"\n')
        old = scan(self.p)
        header.write_text('#include "extra.h"\n')
        result = scan(self.p, old)
        self.assertEqual(result['actual']['main.o'], ['extra.h', 'list.inc', 'main.c'])
        self.assertEqual(result['reused'], ['helper.o'])

    def test_optional_header_appearing_changes_graph(self):
        (self.p / 'main.c').write_text(
            '#if __has_include("optional.inc")\n#include "optional.inc"\n#endif\n')
        old = scan(self.p)
        (self.p / 'optional.inc').write_text('/* now present */\n')
        self.assertEqual(scan(self.p, old)['actual']['main.o'], ['main.c', 'optional.inc'])

    def test_patch_preserves_redundant_dependency(self):
        r=scan(self.p);diff,plan=patch(self.p,r)
        self.assertIn('+main.o: main.c unused.h config.h',diff)
        self.assertNotIn('-\tgcc',diff)
        self.assertNotIn('config.h',(self.p/'Makefile').read_text())

    def test_old_report_rejected(self):
        r=scan(self.p);r['commit']='0'*40
        with self.assertRaisesRegex(ValueError,'STALE_REPORT'):patch(self.p,r)

    def test_unsafe_dependency_rejected(self):
        r=scan(self.p);r['findings']=[{'type':'MISSING','target':'main.o','dependency':'../outside.h'}]
        with self.assertRaisesRegex(ValueError,'UNSAFE_PATH'):patch(self.p,r)

    def test_unsupported_configuration_rejected(self):
        (self.p/'Makefile').write_text((self.p/'Makefile').read_text().replace('-O0','-include unknown.h'))
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_FLAGS'):scan(self.p)

# 将个人测试纳入课程指定的 test_profile.py 发现入口。
from test_student_241880465 import Student241880465Tests
from test_student_241880444 import Student241880444Tests

if __name__=='__main__':unittest.main()
