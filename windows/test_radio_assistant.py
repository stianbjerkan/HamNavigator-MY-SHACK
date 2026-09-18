import copy
import json
import math
from pathlib import Path
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import radio_assistant as app


def string(value):
    raw = value.encode('utf-8')
    return struct.pack('>I', len(raw)) + raw


def packet(kind, payload):
    return struct.pack('>III', 0xadbccbda, 3, kind) + string('WSJT-X-test') + payload


class RadioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous_dir, self.previous_state = app.DATA_DIR, app.STATE
        app.DATA_DIR = Path(self.temp.name)
        app.STATE = copy.deepcopy(app.DEFAULTS)

    def tearDown(self):
        app.set_udp(False)
        app.DATA_DIR, app.STATE = self.previous_dir, self.previous_state
        self.temp.cleanup()

    def qso(self, **extra):
        return {'CALL':'LA1ABC','QSO_DATE':'20260907','TIME_ON':'123456','FREQ':'14.074','MODE':'FT8','GRIDSQUARE':'JO59JH',**extra}

    def test_cloud_exact_duplicates_backed_up_and_distinct_contacts_kept(self):
        first=app.validate_qso(self.qso())
        second={**first,'id':'other-device-id'}
        later=app.validate_qso(self.qso(TIME_ON='124456'))
        app.STATE['qsos']=[first,second,later]
        snap=app.cloud_snapshot()
        self.assertEqual(len([k for k in snap if k.startswith('qso/')]),2)
        self.assertEqual(len(app.STATE['qsos']),2)
        backups=list((app.DATA_DIR/'cloud/duplicate-backups').glob('*.json'))
        self.assertEqual(len(json.loads(backups[0].read_text())['qsos']),3)
        app.cloud_snapshot()
        self.assertEqual(len(app.STATE['qsos']),2)

    def test_cloud_conflicting_duplicates_do_not_silently_overwrite(self):
        first=app.validate_qso(self.qso(COMMENT='One'))
        second={**first,'id':'other','COMMENT':'Two'}
        app.STATE['qsos']=[first,second]
        with self.assertRaisesRegex(ValueError,'Duplikatkontroll'):app.cloud_snapshot()
        self.assertEqual(app.STATE['qsos'],[first,second])

    def test_cloud_same_contact_on_two_pcs_has_same_key_and_no_reimport(self):
        first=app.validate_qso(self.qso())
        app.STATE['qsos']=[first]
        snap=app.cloud_snapshot()
        app.STATE['qsos']=[{**first,'id':'pc-two'}]
        other=app.cloud_snapshot()
        self.assertEqual(snap,other)
        qso_changes={k:v for k,v in snap.items() if k.startswith('qso/')}
        app.cloud_apply(qso_changes,other)
        app.cloud_apply(qso_changes,app.cloud_snapshot())
        self.assertEqual(len(app.STATE['qsos']),1)

    def test_module_selection_persists_without_removing_data(self):
        app.STATE['qsos'] = [app.validate_qso(self.qso())]
        app.modules_update(['utc'])
        app.load_state()
        self.assertEqual(app.STATE['settings']['modules'], ['utc'])
        self.assertEqual(len(app.STATE['qsos']), 1)
        app.settings_update({'radio_notes': 'Keep modules'})
        self.assertEqual(app.STATE['settings']['modules'], ['utc'])
        app.modules_update([])
        self.assertEqual(app.STATE['settings']['modules'], [])
        with self.assertRaises(ValueError): app.modules_update(['unknown'])
        with self.assertRaises(ValueError): app.modules_update('utc')
        with self.assertRaises(ValueError): app.modules_update([{}])
        self.assertEqual(app.STATE['settings']['modules'], [])

    def test_module_defaults_for_existing_data_and_save_failure(self):
        app.STATE['settings'].pop('modules')
        app.persist()
        app.load_state()
        self.assertEqual(app.STATE['settings']['modules'], app.MODULE_IDS)
        with patch.object(app, 'persist', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): app.modules_update(['utc'])
        self.assertEqual(app.STATE['settings']['modules'], app.MODULE_IDS)

    def test_grid_roundtrip_and_known_coordinates(self):
        self.assertEqual(app.point_grid(59.91,10.75),'JO59JV')
        for grid in ('AA00AA','RR99XX','JO59JH','FN31PR','JJ00AA'):
            point=app.grid_point(grid)
            self.assertEqual(app.point_grid(point['lat'],point['lon']),grid)
        p=app.grid_point('JO59')
        self.assertEqual(p,{'lat':59.5,'lon':11})
        with self.assertRaises(ValueError):app.grid_point('ZZ99')
        with self.assertRaises(ValueError):app.point_grid(float('nan'),1)
        with self.assertRaises(ValueError):app.point_grid(90,180)

    def test_distance_bearing(self):
        route=app.path_between('JO59JH','FN31PR')
        self.assertTrue(5600<route['km']<6100)
        self.assertTrue(280<route['bearing']<305)
        self.assertEqual(app.path_between('JO59JH','JO59JH')['bearing'],None)
        back=app.path_between('FN31PR','JO59JH')
        self.assertEqual(route['km'],back['km'])

    def test_adif_length_boundaries_and_roundtrip(self):
        q=app.validate_qso(self.qso(COMMENT='Literal <EOR> in a note',APP_CUSTOM='retain me'))
        encoded=app.export_adif([q])
        rows=app.parse_adif(encoded)
        self.assertEqual(rows[0]['COMMENT'],'Literal <EOR> in a note')
        self.assertEqual(rows[0]['APP_CUSTOM'],'retain me')
        self.assertEqual(app.import_adif(encoded)['added'],1)
        self.assertEqual(app.import_adif(encoded)['duplicates'],1)
        app.load_state()
        self.assertEqual(len(app.STATE['qsos']),1)
        with self.assertRaises(ValueError):app.parse_adif('<CALL:99>LA1ABC')
        with self.assertRaises(ValueError):app.parse_adif('<CALL:6>LA1ABC')

    def test_invalid_log_and_ft4_normalization(self):
        with self.assertRaises(ValueError):app.validate_qso(self.qso(FREQ='nan'))
        with self.assertRaises(ValueError):app.validate_qso(self.qso(QSO_DATE='20260230'))
        with self.assertRaises(ValueError):app.validate_qso(self.qso(TIME_ON='246100'))
        q=app.validate_qso(self.qso(MODE='FT4'))
        self.assertEqual((q['MODE'],q['SUBMODE']),('MFSK','FT4'))
        result=app.import_adif(app.export_adif([app.validate_qso(self.qso())])+'<CALL:3>BAD <EOR>')
        self.assertEqual((result['added'],result['invalid']),(1,1))

    def test_unicode_backup_and_ascii_adif(self):
        q=app.validate_qso(self.qso(COMMENT='Blåbær på øya'))
        app.STATE['qsos']=[q];app.persist();app.load_state()
        self.assertEqual(app.STATE['qsos'][0]['COMMENT'],'Blåbær på øya')
        self.assertIn('Blabaer pa oya',app.export_adif([q]))
        app.persist()
        self.assertTrue((app.DATA_DIR/'data.previous.json').exists())

    def test_wsjt_status_decode_and_logged_adif(self):
        payload=struct.pack('>Q',14074000)+string('FT8')+string('LA1ABC')+string('-12')+string('FT8')+struct.pack('>???II',True,False,False,1000,1500)+string('LA9XYZ')+string('JO59JH')+string('JO59JV')
        event=app.decode_packet(packet(1,payload))
        self.assertEqual(event['freq'],14.074)
        self.assertEqual(event['call'],'LA9XYZ')
        payload=struct.pack('>?IidI',True,45296000,-14,.2,1340)+string('~')+string('CQ LA1ABC JO59')+struct.pack('>??',False,False)
        event=app.decode_packet(packet(2,payload))
        self.assertEqual(event['message'],'CQ LA1ABC JO59')
        self.assertEqual(event['snr'],-14)
        self.assertFalse(event['off_air'])
        for data in (b'bad',packet(2,payload)[:25]):
            with self.assertRaises((ValueError,struct.error)):app.decode_packet(data)
        adif=app.export_adif([app.validate_qso(self.qso())])
        event=app.decode_packet(packet(12,string(adif)))
        self.assertEqual(app.import_adif(event['adif'])['added'],1)

    def test_udp_socket_end_to_end_and_port_conflict(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as available:
            available.bind(('127.0.0.1',0));port=available.getsockname()[1]
        app.set_udp(True,port)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sender:
            adif=app.export_adif([app.validate_qso(self.qso())])
            sender.sendto(packet(12,string(adif)),('127.0.0.1',port))
        deadline=time.time()+3
        while not app.STATE['qsos'] and time.time()<deadline:time.sleep(.02)
        self.assertEqual(len(app.STATE['qsos']),1)
        app.set_udp(False)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as occupied:
            occupied.bind(('127.0.0.1',0))
            with self.assertRaises(ValueError):app.set_udp(True,occupied.getsockname()[1])

    def test_repeater_and_cluster_parser(self):
        row=app.validate_repeater({'name':'Test','rx':'145,650','shift':'-0,6','grid':'JO59JH'})
        self.assertAlmostEqual(row['rx']+row['shift'],145.05)
        with self.assertRaises(ValueError):app.validate_repeater({'name':'Test','rx':'0.1','shift':'-1'})
        spot=app.parse_spot('DX de LA9XYZ:    14074.0  JA1ABC       FT8 CQ 1234Z')
        self.assertEqual(spot['call'],'JA1ABC')
        self.assertEqual(spot['band'],'20m')
        self.assertEqual(spot['freq'],14.074)
        self.assertIsNone(app.parse_spot('Welcome to the cluster'))

    def test_local_cluster_connection_and_receive(self):
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen(1)
        received=[]
        def remote():
            conn,_=server.accept()
            with conn:
                received.append(conn.recv(200).decode())
                conn.sendall(b'DX de LA9XYZ:  14074.0 JA1ABC FT8 1234Z\r\n')
        thread=threading.Thread(target=remote);thread.start()
        app.LIVE['dx']['spots']=[]
        app.dx_loop('127.0.0.1',server.getsockname()[1],'LA1ABC',threading.Event())
        thread.join(2);server.close()
        self.assertEqual(received,['LA1ABC\r\n'])
        self.assertEqual(app.LIVE['dx']['spots'][0]['call'],'JA1ABC')

    def test_mshv_protocol_schema2_and_schema3(self):
        payload = struct.pack('>Q', 144360000) + string('MSK144') + string('LA1ABC') + string('+04') + string('MSK144') + struct.pack('>???II', False, False, True, 0, 0) + string('LA9TEST') + string('JO59JH') + string('JO59JV')
        # MSHV appends additional status fields; older receivers must tolerate them.
        payload += struct.pack('>?', False) + string('') + struct.pack('>?BII', False, 0, 0xffffffff, 0xffffffff) + string('Default') + string('CQ LA9TEST JO59')
        for schema in (2, 3):
            event = app.decode_packet(struct.pack('>III', 0xadbccbda, schema, 1) + string('MSHV') + payload)
            self.assertEqual(event['client'], 'MSHV')
            self.assertEqual(event['mode'], 'MSK144')
            self.assertEqual(event['freq'], 144.36)
        heartbeat = struct.pack('>III', 0xadbccbda, 2, 0) + string('MSHV') + struct.pack('>I', 3) + string('2.76.1') + string('')
        self.assertEqual(app.decode_packet(heartbeat)['version'], '2.76.1')

    def test_mshv_simplified_and_framed_log_deduplicate(self):
        record = '<CALL:6>LA1ABC<QSO_DATE:8>20260907<TIME_ON:6>123456<FREQ:7>144.360<MODE:6>MSK144<COMMENT:6>På øya<EOR>'
        plain = '<PROGRAMID:4>MSHV<EOH>' + record
        event = app.decode_packet(plain.encode('utf-8'))
        self.assertEqual(event['client'], 'MSHV (ADIF)')
        self.assertEqual(app.import_adif(event['adif'])['added'], 1)
        framed = struct.pack('>III', 0xadbccbda, 2, 12) + string('MSHV') + string('\n<ADIF_VER:5>3.1.0\n<PROGRAMID:4>MSHV\n<EOH>\n' + record)
        event = app.decode_packet(framed)
        self.assertEqual(app.import_adif(event['adif'])['duplicates'], 1)
        self.assertEqual(app.STATE['qsos'][0]['COMMENT'], 'På øya')
        self.assertEqual(app.STATE['qsos'][0]['BAND'], '2m')
        with self.assertRaises(ValueError):
            app.decode_packet(b'<PROGRAMID:4>MSHV<EOH><CALL:6>LA1ABC')

    def test_mshv_launch_starts_listener_without_radio_arguments(self):
        executable = app.DATA_DIR / 'MSHV_WIN64.exe'
        executable.write_bytes(b'test placeholder')
        app.STATE['settings']['mshv_path'] = str(executable)
        with patch.object(app.subprocess, 'Popen') as launch, patch.object(app, 'set_udp') as listen, patch.object(app, 'open_desktop', return_value=False):
            app.LIVE['udp']['running'] = False
            app.open_mshv()
            listen.assert_called_once_with(True, 2238)
            launch.assert_called_once_with([str(executable)], cwd=str(executable.parent))


if __name__=='__main__':unittest.main()
