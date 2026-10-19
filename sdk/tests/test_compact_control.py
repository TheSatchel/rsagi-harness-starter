import math,unittest
from rsagi_harness.control import native_fields,view_quaternion,control_schema
from rsagi_harness.protocol import validate_model_decision,ProtocolError,action_schema

class CompactControlTests(unittest.TestCase):
    def decision(self,action,**extra):
        return validate_model_decision({'action':action,'why':'根据可见树干靠近并采木。',**extra})

    def test_sparse_action_needs_no_discriminator_or_unused_fields(self):
        for action in [{},{'vel':[1,0,0]},{'look':[30,-10]},{'do':'mine'},
          {'vel':[.5,-.25,.4],'look':[15,-10],'do':'mine','ticks':20,'slot':1},
          {'mode':'sprint','jump':True},{'type':'WAIT'}]:
            with self.subTest(action=action):self.assertEqual(self.decision(action)['action'],action)

    def test_defaults_stop_previous_inputs_and_hotbar_is_human_numbered(self):
        empty=native_fields({})
        self.assertEqual((empty['type'],empty['forward'],empty['right'],empty['turn'],empty['interaction'],empty['hold_ticks']),('ACT','0','0','0','none','5'))
        self.assertNotIn('hotbar',empty)
        self.assertEqual(native_fields({'slot':1})['hotbar'],'0')
        self.assertEqual(native_fields({'slot':9})['hotbar'],'8')

    def test_forward_right_are_local_strengths_and_diagonal_has_no_speed_bonus(self):
        fields=native_fields({'vel':[1,1,.5]})
        self.assertAlmostEqual(math.hypot(float(fields['forward']),float(fields['right'])),1)
        self.assertEqual(fields['turn'],'0.5')
        self.assertEqual(native_fields({'vel':[.2,-.3,-.5]})['right'],'-0.3')
        self.assertEqual(native_fields({'vel':[.2,-.3,-.5]})['forward'],'0.2')

    def test_look_delta_is_not_repeated_or_changed_by_codec(self):
        fields=native_fields({'look':[15,-10],'ticks':80})
        self.assertEqual((fields['yaw'],fields['pitch'],fields['hold_ticks']),('15','-10','80'))
        self.assertNotIn('yaw_rate',fields)

    def test_invalid_values_cannot_reach_executor(self):
        bad=[{'vel':[True,0,0]},{'vel':[float('nan'),0,0]},{'vel':[1.01,0,0]},
          {'vel':[1]},{'vel':[1,0]},{'vel':[0,0,1.01]},{'vel':[0,0,True]},
          {'vel':(1,0,0)},{'look':[0,91]},{'look':[181,0]},
          {'look':[0,float('inf')]},{'do':'pathfind'},{'do':[]},
          {'ticks':0},{'ticks':81},{'ticks':True},{'slot':0},{'slot':10},
          {'mode':'fly'},{'jump':1},{'type':'INPUT','keys':['forward']},
          {'target_block':[1,2,3]},{'position':[0,70,0]},{'velocity':[10,0,0]},
          {'until':'tree_destroyed'},{'quaternion':[1,0,0,0]}]
        for action in bad:
            with self.subTest(action=action),self.assertRaises(ProtocolError):self.decision(action)

    def test_compact_and_structured_explanations_are_mutually_exclusive(self):
        legacy={'evidence':'树干在准星附近','reason':'需要木头','expected':'开始挖掘'}
        self.assertEqual(validate_model_decision({'action':{'do':'mine'},'explanation':legacy})['explanation'],legacy)
        for value in [{'action':{}},{'action':{},'why':' '},{'action':{},'why':'x'*301},
          {'action':{},'why':'理由','explanation':legacy}]:
            with self.subTest(value=value),self.assertRaises(ProtocolError):validate_model_decision(value)

    def test_no_target_or_semantic_world_data_is_added_to_controls(self):
        allowed={'type','forward','right','turn','yaw','pitch','interaction','hold_ticks','mode','jump','hotbar'}
        for action in [{},{'vel':[1,0,.2],'look':[90,0],'do':'mine','slot':2}]:
            self.assertLessEqual(set(native_fields(action)),allowed)

    def test_quaternion_is_unit_no_roll_and_matches_minecraft_axes(self):
        for yaw in [-180,-90,0,45,180,270,360]:
            for pitch in [-90,-30,0,30,90]:
                w,x,y,z=view_quaternion(yaw,pitch)
                self.assertAlmostEqual(w*w+x*x+y*y+z*z,1)
                # Rotate neutral +Z forward by the quaternion.
                direction=[2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)]
                a=math.radians(yaw);b=math.radians(pitch)
                expected=[-math.sin(a)*math.cos(b),-math.sin(b),math.cos(a)*math.cos(b)]
                for actual,wanted in zip(direction,expected):self.assertAlmostEqual(actual,wanted)
                self.assertGreaterEqual(w,-1e-15)

    def test_schema_contains_sparse_control_and_short_reason(self):
        compact=control_schema();schema=action_schema()
        self.assertNotIn('required',compact)
        self.assertEqual(compact['properties']['ticks']['default'],5)
        self.assertEqual(compact['properties']['slot']['minimum'],1)
        self.assertIn('why',schema['properties']);self.assertEqual(schema['required'],['action'])
        self.assertEqual(len(schema['oneOf']),2)

    def test_compact_decision_reaches_committed_receipt_without_rewriting(self):
        from rsagi_harness import CompetitionClient,complete_round
        from rsagi_harness.mock import MockArena,MockServer
        output={'action':{'vel':[.25,-.5,1],'do':'mine','ticks':10},'why':'采集准星处的方块。'}
        arena=MockArena(teams=('alpha',),rounds=1,model=lambda *args:output)
        with MockServer(arena) as server:
            client=CompetitionClient(server.url,arena.tokens['alpha'],allow_mock=True,expected_match_id=arena.match_id)
            self.assertEqual(client.session()['character_control']['turn_degrees_per_logical_second'],180)
            round_info=client.round();complete_round(client,round_info,choose_credits=lambda _:1)
            self.assertEqual(arena.steps[0]['actions']['alpha'],output['action'])
            self.assertEqual(next(iter(arena.operations.values()))['original_fixture_result'],output)

if __name__=='__main__':unittest.main()
