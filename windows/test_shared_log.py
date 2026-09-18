import copy,json,tempfile,unittest,threading
from pathlib import Path
from shared_log import SharedLog,ID,dump,parse,bridge

def q(uid,day='20260911'):
    return {ID:uid,'CALL':'LA1ABC','QSO_DATE':day,'TIME_ON':'120000','MODE':'FT8','BAND':'20M','STATION_CALLSIGN':'LB7YK','COMMENT':'blå <EOR> tekst'}

class Tests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=SharedLog(self.root);self.s.initialize()
    def tearDown(self):self.tmp.cleanup()
    def test_my_shack_observes_external_save_and_rejects_stale_form(self):
        import io
        from unittest.mock import patch
        import radio_assistant as app
        base=self.s.commit([],[q('a')])
        state=copy.deepcopy(app.DEFAULTS)
        from types import SimpleNamespace
        with patch.object(app,'CLOUD',SimpleNamespace(authorized=True)),patch.object(app,'SHARED',self.s),patch.object(app,'SHARED_BASE',[]),patch.object(app,'STATE',state):
            handler=object.__new__(app.Handler)
            handler.valid_host=lambda:True
            replies=[]
            handler.send=lambda value,status=200,**kw:replies.append((status,value))
            handler.path='/api/state';handler.do_GET()
            stale=copy.deepcopy(replies[-1][1]['qsos'][0])
            handler.path='/api/live';handler.do_GET();revision=replies[-1][1]['log_revision']
            changed=copy.deepcopy(base);changed[0]['COMMENT']='External edit preserved'
            self.s.commit(base,changed)
            handler.do_GET();self.assertNotEqual(revision,replies[-1][1]['log_revision'])
            for path,payload in [('/api/qso',{**stale,'COMMENT':'Stale edit','_expected':stale}),('/api/qso/delete',{'id':'a','_expected':stale})]:
                raw=json.dumps(payload).encode();handler.path=path
                handler.headers={'X-Radio-Token':app.TOKEN,'Content-Length':str(len(raw))};handler.rfile=io.BytesIO(raw)
                handler.do_POST();self.assertEqual(replies[-1][0],400)
                self.assertEqual(self.s.read()[0]['COMMENT'],'External edit preserved')
    def test_concurrent_add_preserves_both(self):
        gate=threading.Barrier(2);errors=[]
        def save(uid,day):
            try:gate.wait();self.s.commit([],[q(uid,day)])
            except Exception as e:errors.append(e)
        a=threading.Thread(target=save,args=('a','20260911'));b=threading.Thread(target=save,args=('b','20260912'));a.start();b.start();a.join();b.join()
        self.assertFalse(errors);self.assertEqual(len(self.s.read()),2)
    def test_duplicate_and_different_day(self):
        self.s.commit([],[q('a')]);self.s.commit([],[q('b'),q('c','20260912')]);self.assertEqual(len(self.s.read()),2)
    def test_edit_merge_and_conflict(self):
        base=self.s.commit([],[q('a')]);one=copy.deepcopy(base);one[0]['RST_SENT']='-10';self.s.commit(base,one)
        two=copy.deepcopy(base);two[0]['RST_RCVD']='-12';rows=self.s.commit(base,two);self.assertEqual(rows[0]['RST_SENT'],'-10')
        two[0]['RST_SENT']='-14'
        with self.assertRaises(RuntimeError):self.s.commit(base,two)
        self.assertEqual(self.s.read(),rows)
    def test_delete_cannot_erase_concurrent_edit(self):
        base=self.s.commit([],[q('a')]);changed=copy.deepcopy(base);changed[0]['COMMENT']='Changed';self.s.commit(base,changed)
        with self.assertRaises(RuntimeError):self.s.commit(base,[])
        self.s.commit(changed,[]);self.assertEqual(self.s.read(),[])
    def test_native_projection_does_not_discard_unrepresented_fields(self):
        base=self.s.commit([],[q('a')]);old='<CALL:6>LA1ABC<COMMENT:3>old<EOR>'
        new='<CALL:6>LA1ABC<COMMENT:3>new<EOR>'
        result=bridge({'action':'commit','canonical':base,'before':[{'id':'a','adif':old}],'after':[{'id':'a','adif':new}]},self.s)
        self.assertEqual(result['rows'][0]['COMMENT'],'new');self.assertEqual(result['rows'][0]['STATION_CALLSIGN'],'LB7YK')
        self.assertEqual(result['baseline'][0]['COMMENT'],'new')
    def test_unicode_roundtrip_and_truncation(self):
        self.assertEqual(parse(dump([q('a')])),[q('a')])
        with self.assertRaises(ValueError):parse('<CALL:99>short')
    def test_migration_retains_originals_and_restarts_once(self):
        root=self.root/'fresh';root.mkdir();(root/'data.json').write_text(json.dumps({'settings':{},'qsos':[q('a'),q('b','20260912')]}))
        s=SharedLog(root);self.assertEqual(len(s.initialize()),2)
        (root/'data.json').write_text('{}');self.assertEqual(len(s.initialize()),2)
        self.assertTrue(list((root/'log/migration-originals').glob('*data.json')))

if __name__=='__main__':unittest.main()
