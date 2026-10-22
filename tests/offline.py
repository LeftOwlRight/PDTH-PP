"""Run with Python + lupa (LuaJIT): no game process, Steam or desktop access.

PDTH_SOURCE and DAHM_CORE may point at separate game-Lua and dahm checkouts.
The defaults use the sibling references prepared for this workspace.
"""
import os
from pathlib import Path
import unittest
from lupa.luajit21 import LuaRuntime

REPO = Path(__file__).resolve().parents[1]
MOD = REPO / 'mods/PDTH++'
SOURCE = Path(os.environ.get('PDTH_SOURCE', REPO.parent / 'pdth-source'))
CORE = Path(os.environ.get('DAHM_CORE', REPO.parent / 'dahm/release-20261020/mods/core'))

BOOT = r'''
now=0; server=true; settings={}; release='1.36.0.9'
function alive(u) return u ~= nil and not u.dead end
function Idstring(s) return s end
function class(p) return setmetatable({super=p},{__index=p}) end
function Vector3(x,y,z) return {x=x or 0,y=y or 0,z=z or 0} end
mvector3={}
function mvector3.set(a,b) a.x,a.y,a.z=b.x,b.y,b.z end
function mvector3.direction(out,a,b)
 local x,y,z=b.x-a.x,b.y-a.y,b.z-a.z;local d=math.sqrt(x*x+y*y+z*z)
 out.x,out.y,out.z=x/d,y/d,z/d;return d
end
function mvector3.dot(a,b) return a.x*b.x+a.y*b.y+a.z*b.z end
function mvector3.distance(a,b) return math.sqrt((a.x-b.x)^2+(a.y-b.y)^2+(a.z-b.z)^2) end
function math.clamp(n,a,b) return math.max(a,math.min(b,n)) end
function mvector3.negate() end
function mvector3.spread() end
tablex={get=function(t,k) return t and t[k] end}
Application={time=function() return now end}
TimerManager={game=function() return {time=function() return now end} end}
World={make_slot_mask=function() return 8 end}
Network={is_server=function() return server end,is_client=function() return not server end}
managers={}
core={__obj2nametable={},__modules={}}
D={conf=function(self,k) return settings[k] end,_log=function() end}
module={classes={},events={}}
function module:id() return 'PDTH++' end
function module:version() return release end
function module:active_script_override() return {} end
function module:log() end
function module:hook_class(name,default,...)
 local c=self.classes[name] or rawget(_G,name) or (default and default(...)) or {}
 self.classes[name]=c;return c
end
function D:module(id) if id=='PDTH++' then return module end end
function module:emit(event,...)
 for _,fn in pairs(self.events[event] or {}) do fn(...) end
end
'''


def lua_runtime():
    l = LuaRuntime(unpack_returned_tuples=True)
    l.execute(BOOT)
    l.globals().hooker = l.execute((CORE / 'objecthooker.lua').read_text(), l.globals().D)
    l.execute('''
    function module:hook(obj,name,...)
      if type(obj)=='string' then
        local fn
        for i=1,select('#',...) do local v=select(i,...);if type(v)=='function' then fn=v end end
        self.events[obj]=self.events[obj] or {};self.events[obj][name]=fn
      else return hooker:add_hook(self,4,obj,name,false,...) end
    end
    function module:pre_hook(obj,name,fn,has_ret) return hooker:add_hook(self,5,obj,name,false,fn,has_ret) end
    function module:post_hook(obj,name,fn,has_ret) return hooker:add_hook(self,6,obj,name,false,fn,has_ret) end
    function module:call_orig(obj,name,...) return hooker:call_original_s(self,obj,name,false,false,...) end
    ''')
    return l


def load(l, path):
    l.execute((MOD / path).read_text(encoding='utf-8-sig'), l.globals().module)


def native(l, path):
    l.execute((SOURCE / path).read_text(encoding='utf-8-sig'))


def to_python(v):
    if hasattr(v, 'items'):
        return {k: to_python(x) for k, x in v.items()}
    return v


ECONOMY = r'''
equipment={amount=0}
ammo={_ammo_total=100,_ammo_max=100,_ammo_remaining_in_clip=20}
gun={base=function() return ammo end}
player={position=function() return Vector3() end,
 character_damage=function() return {dead=function() return false end} end,
 inventory=function() return {available_selections=function() return {{unit=gun}} end} end}
interaction={}
base={get_name_id=function() return 'sentry_gun' end,
 server_information=function() return {owner_peer_id=2} end}
sentry_weapon={_ammo_total=200,_ammo_max=400}
sentry_damage={_health=10,_health_max=10}
sentry={id=function() return 42 end,position=function() return Vector3(100,0,0) end,
 base=function() return base end,weapon=function() return sentry_weapon end,
 character_damage=function() return sentry_damage end,interaction=function() return interaction end}
destroy_count=0
function base:destroy_sentry()
 destroy_count=destroy_count+1;module:pdthpp_forget_sentry(sentry);sentry.dead=true
end
World.find_units_quick=function() return sentry.dead and {} or {sentry} end
remote={id=function() return server and 2 or 1 end,user_id=function() return server and 'client' or 'host' end,
 is_local_user=function() return false end,is_server=function() return not server end}
local_peer={id=function() return server and 1 or 2 end,is_local_user=function() return true end}
session={server_peer=function() return remote end,local_peer=function() return local_peer end}
managers.network={session=function() return session end,game=function()
 return {unit_from_peer_id=function() return player end} end}
managers.player={player_unit=function() return player end,equipment_data_by_name=function() return equipment,1 end}
tweak_data={interaction={sentry_gun={interact_distance=200}}}
packets={};send_ok=true
function send(kind,data)
 if not send_ok then return false end
 packets[#packets+1]={kind=kind,data=data};return true
end
DNet={send_to_peer=function(self,peer,kind,data) return send(kind,data) end,
 send_to_peers=function(self,kind,data) return send(kind,data) end,
 send_to_peers_synched=function(self,kind,data) return send(kind,data) end}
RequiredScript='audit'
'''


def economy(server):
    l = lua_runtime()
    l.globals().server = server
    load(l, 'deployables/sentrynetwork.lua')
    l.execute(ECONOMY)
    load(l, 'deployables/sentryammo.lua')
    return l


def pair():
    h, c = economy(True), economy(False)
    c.globals().base['_pdthpp_instance'] = h.eval('module:pdthpp_sentry_instance(sentry)')
    return h, c


def begin(c):
    return c.execute('plan=module:pdthpp_build_sentry_pickup_cost_plan(player,0.3);return module:pdthpp_begin_sentry_pickup(sentry,plan)')


def packet(l, index=-1):
    q = l.globals().packets
    return to_python(q[len(q) if index == -1 else index])


def deliver(l, p):
    data = l.table_from(p['data'], recursive=True)
    l.eval('function(kind,data) module:pdthpp_handle_sentry_network(remote,kind,data) end')(p['kind'], data)


class OfflineTests(unittest.TestCase):
    def test_all_lua_compiles(self):
        l = lua_runtime()
        compile_only = l.eval('function(s,n) local f,e=loadstring(s,n);return f~=nil,e end')
        for p in MOD.rglob('*.lua'):
            ok, error = compile_only(p.read_text(encoding='utf-8-sig'), str(p))
            self.assertTrue(ok, error)

    def test_release_numbers_do_not_gate(self):
        tokens = []
        for release in ['1.36.0.8', '1.36.0.9', '2.99.123', 'dev-test']:
            l = lua_runtime();l.globals().release = release
            load(l, 'sandbox/networkcompat.lua')
            l.execute('NetworkMatchMakingSTEAM={_BUILD_SEARCH_INTEREST_KEY="1.23.0"}')
            load(l, 'sandbox/networkmatchmakingsteam.lua')
            key = l.eval('NetworkMatchMakingSTEAM._BUILD_SEARCH_INTEREST_KEY')
            # Regression for 9a38577: release/protocol strings must not be fed to %d.
            self.assertEqual(key, '1.23.0-PDTH++-protocol-2')
            load(l, 'sandbox/networkmatchmakingsteam.lua')
            self.assertEqual(key, l.eval('NetworkMatchMakingSTEAM._BUILD_SEARCH_INTEREST_KEY'))
            tokens.append(l.eval('module:pdthpp_protocol_token()'))
        self.assertEqual(len(set(tokens)), 1)

    def test_game_version_and_protocol_gate(self):
        l = lua_runtime();load(l, 'sandbox/networkcompat.lua')
        l.execute('module._pdthpp_game_build="1.23.0"')
        verify = l.eval('function(s) return module:pdthpp_clean_protocol_tokens(s) end')
        token = l.eval('module:pdthpp_protocol_token()')
        self.assertEqual(verify('dlc1 ' + token), (True, 'protocol', 'dlc1'))
        for value in ['', 'pdthpp_protocol_1.36.0.9', 'pdthpp_protocol_3-game-1.23.0', token + ' pdthpp_protocol_wrong']:
            self.assertFalse(verify(value)[0])
        self.assertEqual(verify('pdthpp_protocol_2-game-1.21.0')[1], 'game')

    def test_protocol_marker_pattern_boundaries(self):
        l = lua_runtime();load(l, 'sandbox/networkcompat.lua')
        l.execute('module._pdthpp_game_build="1.23.0"')
        verify = l.eval('function(s) return module:pdthpp_clean_protocol_tokens(s) end')
        token = 'pdthpp_protocol_2-game-1.23.0'
        for whitespace in [' ', '\t', '\r\n', '\v\f']:
            with self.subTest(whitespace=repr(whitespace)):
                valid, _, cleaned = verify(whitespace.join(['dlc1', token, token, 'dlc2']))
                self.assertTrue(valid)
                self.assertEqual(cleaned, 'dlc1 dlc2')
        for marker, reason in [
            ('pdthpp_protocol_2-game-1.22.0', 'game'),
            ('pdthpp_protocol_3-game-1.23.0', 'protocol'),
            ('pdthpp_protocol_2-game-1x23x0', 'game'),
            ('pdthpp_protocol_2XgameX1.23.0', 'protocol'),
            (token + '-extra', 'protocol'),
            (token + '.', 'game'),
            ('pdthpp_protocol_-game-1.23.0', 'protocol'),
            ('pdthpp_protocol_2-game-', 'protocol'),
            ('x' + token, 'missing'),
        ]:
            with self.subTest(marker=marker):
                valid, actual_reason, cleaned = verify('dlc1 ' + marker + ' dlc2')
                self.assertFalse(valid)
                self.assertEqual(actual_reason, reason)
                self.assertEqual(cleaned, 'dlc1 dlc2' if reason != 'missing' else 'dlc1 ' + marker + ' dlc2')

    def test_rejection_reason_pattern_and_sender(self):
        l = lua_runtime()
        l.execute('''
        ConnectionNetworkHandler={join_request_reply=function()
          observed_reason=module._pdthpp_join_rejection and module._pdthpp_join_rejection.reason
          return 'original-result'
        end}
        local host={user_id=function() return 'host' end,ip=function() return 'host-ip' end}
        managers.network={session=function() return {server_peer=function() return host end} end}
        sender={ip_at_index=function() return sender_ip end};sender_ip='host-ip'
        ''')
        load(l, 'sandbox/connectionnetworkhandler.lua')
        reply = l.eval('function(mask,user) return ConnectionNetworkHandler:join_request_reply(2,0,1,1,0,mask,user,sender) end')
        for mask in ['pdthpp_reject_missing', 'pdthpp_reject_protocol', 'pdthpp_reject_game',
                     'xpdthpp_reject_game', 'pdthpp_reject_gamex', 'pdthpp_reject_game\n',
                     'pdthpp_reject_', 'pdthpp_reject_game-extra', 'pdthpp_reject_GAME', 0]:
            with self.subTest(mask=mask):
                self.assertEqual(reply(mask, 'host'), 'original-result')
                expected = {'pdthpp_reject_missing': 'missing', 'pdthpp_reject_protocol': 'protocol',
                            'pdthpp_reject_game': 'game'}.get(mask)
                self.assertEqual(l.globals().observed_reason, expected)
                self.assertIsNone(l.eval('module._pdthpp_join_rejection'))
        reply('pdthpp_reject_game', 'other-user')
        self.assertIsNone(l.globals().observed_reason)
        l.globals().sender_ip = 'other-ip'
        reply('pdthpp_reject_game', 'host')
        self.assertIsNone(l.globals().observed_reason)

    def test_dlc_marker_is_replaced_and_deduplicated(self):
        l=lua_runtime();load(l,'sandbox/networkcompat.lua')
        l.execute('module._pdthpp_game_build="1.23.0";GenericDLCManager={dlcs_string=function() return original end}')
        load(l,'sandbox/dlcmanager.lua')
        for original in ['', 'dlc1', 'dlc1 pdthpp_protocol_old pdthpp_protocol_2-game-1.23.0']:
            l.globals().original=original
            value=l.eval('GenericDLCManager:dlcs_string()')
            self.assertEqual(value.count('pdthpp_protocol_'),1)
            if original: self.assertTrue(value.startswith('dlc1 '))

    def test_join_hook_and_isolation_switch(self):
        l=lua_runtime();load(l,'sandbox/networkcompat.lua')
        l.execute('''
        module._pdthpp_game_build='1.23.0'
        ConnectionNetworkHandler={request_join=function(self,n,m,dlcs) accepted=dlcs end}
        Steam={userid=function() return 'host' end};SystemInfo={platform=function() return 'WIN32' end}
        managers.network={session=function() return {local_peer=function() return {user_id=function() return 'host' end} end} end}
        sender={ip_at_index=function() return 'ip' end,join_request_reply=function(self,r,a,b,c,d,mask) rejected=mask end}
        ConnectionNetworkHandler._verify_in_server_session=function() return true end
        ''')
        load(l,'sandbox/connectionnetworkhandler.lua')
        for dlcs, isolated, accepted in [('dlc1', True, False),('dlc1',False,True),('dlc1 pdthpp_protocol_2-game-1.23.0',True,True)]:
            l.globals().dlcs=dlcs;l.globals().settings['network_isolation']=isolated
            l.execute("accepted=nil;rejected=nil;ConnectionNetworkHandler:request_join('name','mask',dlcs,'ip','user','host',sender)")
            self.assertEqual(l.globals().accepted is not None,accepted)
            if accepted:self.assertEqual(l.globals().accepted,'dlc1')

    def test_pickup_escrow_survives_ammo_change(self):
        h,c=pair();self.assertTrue(begin(c));self.assertEqual(c.eval('ammo._ammo_total'),70)
        c.execute('ammo._ammo_total=0')
        request=packet(c);deliver(h,request);response=packet(h)
        self.assertTrue(response['data']['success']);deliver(c,response)
        self.assertEqual(c.eval('equipment.amount'),1)
        self.assertEqual(c.eval('ammo._ammo_total'),0)
        deliver(h,request);deliver(c,packet(h))
        self.assertEqual(h.eval('destroy_count'),1)
        self.assertEqual(c.eval('equipment.amount'),1)

    def test_immediate_send_failure_refunds(self):
        h,c=pair();c.execute('send_ok=false')
        self.assertFalse(begin(c));self.assertEqual(c.eval('ammo._ammo_total'),100)
        self.assertFalse(c.eval('module:pdthpp_sentry_pickup_pending()'))
        self.assertIsNone(c.eval('interaction._pdthpp_pickup_requested'))

    def test_network_unit_zero_is_valid(self):
        h,c=pair()
        for l in [h,c]: l.execute('sentry.id=function() return 0 end')
        self.assertTrue(begin(c));deliver(h,packet(c));deliver(c,packet(h))
        self.assertEqual(c.eval('equipment.amount'),1)

    def test_authoritative_rejection_refunds_once(self):
        h,c=pair();begin(c)
        h.execute('player.position=function() return Vector3(2000,0,0) end')
        deliver(h,packet(c));result=packet(h);deliver(c,result);deliver(c,result)
        self.assertEqual(h.eval('destroy_count'),0)
        self.assertEqual(c.eval('ammo._ammo_total'),100)
        self.assertEqual(c.eval('equipment.amount'),0)

    def test_commit_response_loss_retries_without_second_destroy(self):
        h,c=pair();begin(c);request=packet(c)
        h.execute('send_ok=false');deliver(h,request)
        self.assertEqual(h.eval('destroy_count'),1)
        h.execute('send_ok=true');c.execute('now=2;module:pdthpp_update_sentry_network()')
        deliver(h,packet(c));deliver(c,packet(h))
        self.assertEqual(h.eval('destroy_count'),1)
        self.assertEqual(c.eval('equipment.amount'),1)

    def test_cancel_before_request_is_a_tombstone(self):
        h,c=pair();begin(c);request=packet(c)
        c.execute('now=9;module:pdthpp_update_sentry_network()')
        self.assertEqual(c.eval('ammo._ammo_total'),70)  # no blind timeout refund
        deliver(h,packet(c));result=packet(h);deliver(c,result)
        deliver(h,request)
        self.assertEqual(h.eval('destroy_count'),0)
        self.assertEqual(c.eval('ammo._ammo_total'),100)

    def test_cancel_after_commit_obtains_success(self):
        h,c=pair();begin(c);deliver(h,packet(c))
        c.execute('now=9;module:pdthpp_update_sentry_network()')
        deliver(h,packet(c));deliver(c,packet(h))
        self.assertEqual(c.eval('equipment.amount'),1)
        self.assertEqual(c.eval('ammo._ammo_total'),70)

    def test_stale_unit_instance_cannot_destroy_replacement(self):
        h,c=pair();begin(c)
        h.execute('base._pdthpp_instance="new-unit-instance"')
        deliver(h,packet(c));deliver(c,packet(h))
        self.assertEqual(h.eval('destroy_count'),0)
        self.assertEqual(c.eval('ammo._ammo_total'),100)

    def test_destroy_before_result_keeps_pending(self):
        h,c=pair();begin(c);deliver(h,packet(c))
        deliver(c,packet(h,1))
        self.assertTrue(c.eval('sentry.dead'))
        self.assertTrue(c.eval('module:pdthpp_sentry_pickup_pending()'))
        deliver(c,packet(h))
        self.assertEqual(c.eval('equipment.amount'),1)

    def test_forged_result_ignored(self):
        h,c=pair();begin(c);deliver(h,packet(c))
        c.execute('remote.is_server=function() return false end')
        deliver(c,packet(h));self.assertEqual(c.eval('equipment.amount'),0)
        self.assertTrue(c.eval('module:pdthpp_sentry_pickup_pending()'))

    def test_session_exit_clears_and_refunds_escrow(self):
        h,c=pair();begin(c)
        c.execute('module:emit("OnExitedLobby")')
        self.assertFalse(c.eval('module:pdthpp_sentry_pickup_pending()'))
        self.assertEqual(c.eval('ammo._ammo_total'),100)
        self.assertIsNone(c.eval('interaction._pdthpp_pickup_requested'))

    def test_status_request_rate_and_retries(self):
        h,c=pair()
        for _ in range(20):
            deliver(h,{'kind':'PDTHPPSentryStatusRequest','data':{'module':'PDTH++','unit_id':42,'query':'test-query'}})
        self.assertEqual(len(h.globals().packets),1)
        c.execute('module:pdthpp_request_exact_sentry_status(sentry,false)')
        for second in [1,2,3,4]:
            c.globals().now=second;c.execute('module:pdthpp_update_sentry_network()')
        self.assertEqual(len(c.globals().packets),3)
        c.execute('module:pdthpp_forget_sentry(sentry)')
        self.assertIsNone(c.eval('next(module._pdthpp_sentry_status_request_times)'))

    def test_status_out_of_order_and_no_gameplay_ammo_write(self):
        h,c=pair()
        data={'module':'PDTH++','unit_id':42,'instance':c.eval('base._pdthpp_instance'),
              'revision':2,'ammo_ratio':0.5,'health_ratio':1,'ammo_total':200,'ammo_max':400}
        deliver(c,{'kind':'PDTHPPSentryStatus','data':data})
        data=dict(data,revision=1,ammo_ratio=0.9)
        deliver(c,{'kind':'PDTHPPSentryStatus','data':data})
        self.assertEqual(c.eval('sentry_weapon._pdthpp_exact_ammo_ratio'),0.5)
        self.assertEqual(c.eval('sentry_weapon._ammo_total'),200)

    def test_initial_status_requires_this_units_query(self):
        h,c=pair();c.execute('base._pdthpp_instance=nil;module:pdthpp_request_exact_sentry_status(sentry,false)')
        request=packet(c)
        # A late status for another incarnation must not bind this new unit.
        stale={'module':'PDTH++','unit_id':42,'instance':'stale','revision':99,
               'query':'old-query','ammo_ratio':0,'health_ratio':0}
        deliver(c,{'kind':'PDTHPPSentryStatus','data':stale})
        deliver(c,{'kind':'PDTHPPSentryDestroyed','data':dict(stale)})
        self.assertIsNone(c.eval('base._pdthpp_instance'))
        self.assertFalse(bool(c.eval('sentry.dead')))
        deliver(h,request);deliver(c,packet(h))
        self.assertEqual(c.eval('base._pdthpp_instance'),h.eval('base._pdthpp_instance'))
        deliver(c,{'kind':'PDTHPPSentryStatus','data':stale})
        self.assertEqual(c.eval('base._pdthpp_instance'),h.eval('base._pdthpp_instance'))

    def test_missing_unit_response_is_query_bound(self):
        h,c=pair();c.execute('base._pdthpp_instance=nil;module:pdthpp_request_exact_sentry_status(sentry,false)')
        h.execute('sentry.dead=true');deliver(h,packet(c))
        response=packet(h);self.assertEqual(response['kind'],'PDTHPPSentryMissing')
        wrong=dict(response['data'],query='other-unit')
        deliver(c,{'kind':response['kind'],'data':wrong})
        self.assertFalse(bool(c.eval('sentry.dead')))
        deliver(c,response);self.assertTrue(c.eval('sentry.dead'))

    def test_refund_and_ammo_distribution(self):
        l=economy(False)
        l.execute('''
        other={_ammo_total=1,_ammo_max=100};excluded={_ammo_total=5,_ammo_max=5,pickup_disabled=function() return true end}
        player.inventory=function() return {available_selections=function() return {
          {unit=gun},{unit={base=function() return other end}},{unit={base=function() return excluded end}}} end} end
        plan=module:pdthpp_build_sentry_pickup_cost_plan(player,0.3)
        assert(module:pdthpp_apply_sentry_pickup_cost_plan(plan))
        ''')
        self.assertEqual(l.eval('ammo._ammo_total'),71)
        self.assertEqual(l.eval('other._ammo_total'),0)
        self.assertEqual(l.eval('excluded._ammo_total'),5)
        l.execute('module:pdthpp_refund_sentry_pickup(plan);module:pdthpp_refund_sentry_pickup(plan)')
        self.assertEqual(l.eval('ammo._ammo_total'),100)
        self.assertEqual(l.eval('other._ammo_total'),1)

    def test_refund_restores_untouched_clip(self):
        l=economy(False)
        l.execute('''
        ammo._ammo_total=30;ammo._ammo_remaining_in_clip=30
        plan=module:pdthpp_build_sentry_pickup_cost_plan(player,0.3)
        module:pdthpp_apply_sentry_pickup_cost_plan(plan)
        assert(ammo._ammo_remaining_in_clip==0)
        module:pdthpp_refund_sentry_pickup(plan)
        ''')
        self.assertEqual(l.eval('ammo._ammo_remaining_in_clip'),30)

    def test_fire_rate_and_hitch_no_burst(self):
        for fps in [30,60,144,300]:
            for is_server in [True,False]:
                l=economy(is_server)
                native(l,'lib/units/weapons/sentrygunweapon.lua')
                l.execute('''
                RequiredScript='lib/units/weapons/sentrygunweapon'
                tweak_data.weapon={sentry_gun={auto={fire_rate=0.05},SPREAD=0}}
                World.effect_manager=function() return {spawn=function() end} end
                w=setmetatable({_next_fire_allowed=0,_name_id='sentry_gun',_ammo_total=10000,_ammo_max=10000,
                 _ammo_sync=1,_ammo_sync_resolution=0.2,_interleaving_fire=1,
                 _timer={time=function() return now end},_muzzle_effect_table={{},{}},
                 _unit={network=function() return {send=function() end} end}}, {__index=SentryGunWeapon})
                w._effect_align={{position=function() return {} end,rotation=function() return {y=function() return {} end} end}}
                w._effect_align[2]=w._effect_align[1];shots=0
                w._fire_raycast=function() shots=shots+1;return {} end
                ''')
                load(l,'deployables/sentryammo.lua')
                # Status synchronization does not participate in this timing test.
                l.execute('module.pdthpp_send_sentry_status=function() end')
                l.globals().fps=fps
                l.execute('for i=0,fps-1 do now=i/fps;w:trigger_held(not server,server) end')
                self.assertEqual(l.globals().shots,20,(fps,is_server))
                l.execute('before=shots;for i=0,74 do now=3+i/300;w:trigger_held(not server,server) end')
                self.assertLessEqual(l.eval('shots-before'),5,(fps,is_server))
                # Backwards game clock must not leave a long accidental cooldown.
                l.execute('now=0;before=shots;w:trigger_held(not server,server)')
                self.assertEqual(l.eval('shots-before'),1)
                if is_server:
                    l.execute('''
                    module.pdthpp_send_sentry_status=function(self,unit,force) final_force=force end
                    now=now+0.1;w._ammo_total=1;w._next_fire_allowed=now
                    w:trigger_held(false,true)
                    ''')
                    self.assertTrue(l.eval('final_force'))

    def test_diagnostics_disabled_does_not_install_hooks(self):
        l=lua_runtime();load(l,'deployables/sentrydiagnostics.lua')
        self.assertIsNone(l.eval('module._pdthpp_sentry_diag_helpers_ready'))

    def brain(self):
        l=lua_runtime();native(l,'lib/units/equipment/sentry_gun/sentrygunbrain.lua')
        load(l,'deployables/sentrygunbrain.lua')
        l.execute('''
        local c=module.classes.SentryGunBrain
        c._pdthpp_is_surrender_target=function() return false end
        c._pdthpp_target_position=function(self,data,out) mvector3.set(out,data.m_com);return true,false,false,shootable end
        c._pdthpp_focus_eligibility=function() return true,false,true end
        shootable=true;shot_count=0;stop_count=0
        local movement={m_head_fwd=function() return Vector3(1,0,0) end,
          set_attention=function() end,warming_up=function() return false end,
          _pdthpp_on_focus_changed=function() end}
        local weapon={out_of_ammo=function() return false end,stop_autofire=function() stop_count=stop_count+1 end,
          start_autofire=function() end,trigger_held=function() shot_count=shot_count+1;return {} end}
        local sentry={weapon=function() return weapon end,id=function() return 42 end,
          network=function() return {send=function() end} end,
          movement=function() return {nav_tracker=function() return nil end} end}
        e1={key=1,m_com=Vector3(14000,0,0),unit={}}
        e2={key=2,m_com=Vector3(100,0,0),unit={}}
        managers.enemy={all_enemies=function() return {} end}
        tweak_data={weapon={sentry_gun={KEEP_FIRE_ANGLE=0.9}}}
        brain=setmetatable({_unit=sentry,_ext_movement=movement,_eye_object_pos=Vector3(),
          _m_head_object_pos=Vector3(),_AI_data={detected_enemies={[1]=e1,[2]=e2},focus_enemy=e1},
          _firing=true,_pdthpp_obstruction_engaged_key=1},{__index=c})
        ''')
        return l

    def test_continuous_fire_new_target_gets_obstruction_hold(self):
        l=self.brain();l.execute('''
        brain._pdthpp_obstruction_avoid_until={[1]=100}
        brain:_choose_focus_enemy(1);brain:_check_fire(1)
        ''')
        self.assertEqual(l.eval('brain._AI_data.focus_enemy.key'),2)
        self.assertEqual(l.eval('brain._pdthpp_obstruction_engaged_key'),2)
        self.assertTrue(l.eval('brain:_pdthpp_update_obstruction_hold(1.1,brain._AI_data.focus_enemy,true)'))
        self.assertFalse(l.eval('brain:_pdthpp_update_obstruction_hold(2.7,brain._AI_data.focus_enemy,true)'))

    def test_direction_weight_keeps_rear_enemy_behind_front(self):
        l=self.brain();l.execute('e2.m_com=Vector3(-100,0,0);brain:_choose_focus_enemy(1)')
        self.assertEqual(l.eval('brain._AI_data.focus_enemy.key'),1)

    def test_fire_rechecks_angle_and_reachability(self):
        l=self.brain();l.execute('shootable=false;brain:_check_fire(1)')
        self.assertEqual(l.eval('shot_count'),0)
        l.execute('shootable=true;brain._firing=true;e1.m_com=Vector3(-100,0,0);brain:_check_fire(2)')
        self.assertEqual(l.eval('shot_count'),0)
        self.assertFalse(l.eval('brain._firing'))

    def test_detection_is_bounded_but_fire_updates_each_frame(self):
        l=self.brain();l.execute('''
        detection=0;fire_checks=0
        brain._chk_enemies_valid=function() end;brain._chk_focus_enemy_valid=function() end
        brain._choose_focus_enemy=function() detection=detection+1 end
        brain._check_fire=function() fire_checks=fire_checks+1 end
        for i=0,299 do brain:update(nil,i/300,1/300) end
        ''')
        self.assertLessEqual(l.eval('detection'),11)
        self.assertEqual(l.eval('fire_checks'),300)

    def test_tank_false_overrides_general_headshot_true(self):
        l=lua_runtime()
        s=(MOD/'deployables/sentrygunmovement.lua').read_text(encoding='utf-8-sig')
        s=s.replace('local SENTRY_HEADSHOT_ENABLED = false','local SENTRY_HEADSHOT_ENABLED = true',1)
        l.execute(s,l.globals().module)
        l.execute('''
        tank={key=function() return 1 end,base=function() return {_tweak_table='tank'} end}
        ordinary={key=function() return 2 end,base=function() return {_tweak_table='cop'} end}
        movement=setmetatable({},{__index=module.classes.SentryGunMovement})
        ''')
        self.assertFalse(l.eval('movement:_pdthpp_intentional_headshot(tank)'))
        self.assertTrue(l.eval('movement:_pdthpp_intentional_headshot(ordinary)'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
