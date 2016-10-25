import json

from engines.server import global_vars
from entities.constants import SolidType
from entities.entity import Entity
from entities.hooks import EntityCondition, EntityPostHook, EntityPreHook
from events import Event
from listeners import OnEntityDeleted, OnLevelInit, OnPlayerRunCommand
from mathlib import Vector
from memory import make_object
from paths import GAME_PATH
from players.constants import PlayerButtons
from players.dictionary import PlayerDictionary

from .info import info


MAPDATA_PATH = GAME_PATH / "mapdata" / "limit_zones"
ZONE_ENTITY_CLASSNAME = "trigger_multiple"

players = PlayerDictionary()
nojump_counters = PlayerDictionary(factory=lambda index: 0)
noduck_counters = PlayerDictionary(factory=lambda index: 0)
speed_cap_seqs = PlayerDictionary(factory=lambda index: list())


def dict_to_vector(dict_):
    return Vector(dict_['x'], dict_['y'], dict_['z'])


class Zone:
    def __init__(self, dict_):
        mins = dict_to_vector(dict_['mins'])
        maxs = dict_to_vector(dict_['maxs'])
        properties = {
            'nojump': dict_['properties']['nojump'],
            'noduck': dict_['properties']['noduck'],
            'speed_cap': dict_['properties']['speed_cap'],
            'teleport': {
                'origin': None,
                'angles': None
            },
            'boost': None,
        }

        if dict_['properties']['teleport']['origin'] is not None:
            properties['teleport']['origin'] = dict_to_vector(
                dict_['properties']['teleport']['origin'])

        if dict_['properties']['teleport']['angles'] is not None:
            properties['teleport']['angles'] = dict_to_vector(
                dict_['properties']['teleport']['angles'])

        if dict_['properties']['boost'] is not None:
            properties['boost'] = dict_to_vector(
                dict_['properties']['boost'])

        self.mins = mins
        self.maxs = maxs
        self._properties = properties

    def __getattr__(self, key):
        return self._properties[key]

    def __setattr__(self, key, value):
        if key in ('mins', 'maxs', '_properties'):
            super().__setattr__(key, value)
        else:
            self._properties[key] = value

    @property
    def origin(self):
        return (self.mins + self.maxs) / 2


class ZonesStorage(list):
    def load_from_file(self):
        if not self.filepath.isfile():
            self.clear()
            return

        with open(self.filepath, 'r') as f:
            json_dict = json.load(f)

        for zone_json in json_dict['zones']:
            self.append(Zone(zone_json))

    @property
    def filepath(self):
        return MAPDATA_PATH / "{basename}.json".format(
            basename=global_vars.map_name)

zones_storage = ZonesStorage()


class ZoneEntity:
    def __init__(self, entity, zone):
        self.entity = entity
        self.zone = zone

zone_entities = {}


def create_zone_entities():
    for zone in zones_storage:
        entity = Entity.create(ZONE_ENTITY_CLASSNAME)
        entity.set_key_value_string(
            "model", "maps/{map_name}.bsp".format(
                map_name=global_vars.map_name))

        entity.spawn()

        entity.solid_type = SolidType.BBOX

        mins = Vector(
            min(zone.mins.x, zone.maxs.x),
            min(zone.mins.y, zone.maxs.y),
            min(zone.mins.z, zone.maxs.z)
        )
        maxs = Vector(
            max(zone.mins.x, zone.maxs.x),
            max(zone.mins.y, zone.maxs.y),
            max(zone.mins.z, zone.maxs.z)
        )

        maxs = (maxs - mins) / 2
        entity.mins = maxs * (-1)
        entity.maxs = maxs
        entity.origin = zone.origin

        zone_entities[entity.index] = ZoneEntity(entity, zone)


def load():
    if global_vars.map_name:
        zones_storage.load_from_file()
        create_zone_entities()


def unload():
    for zone_entity in list(zone_entities.values()):
        zone_entity.entity.remove()


@OnLevelInit
def listener_on_level_init(level_name):
    zones_storage.load_from_file()

    nojump_counters.clear()
    noduck_counters.clear()
    speed_cap_seqs.clear()


@OnEntityDeleted
def listener_on_entity_deleted(base_entity):
    if not base_entity.is_networked():
        return

    zone_entities.pop(base_entity.index, None)


@Event('round_start')
def on_round_start(game_event):
    create_zone_entities()


_ecx_storage_start_touch = {}
_ecx_storage_end_touch = {}


@EntityPreHook(
    EntityCondition.equals_entity_classname(ZONE_ENTITY_CLASSNAME),
    "start_touch")
def pre_start_touch(args):
    entity = make_object(Entity, args[0])
    other = make_object(Entity, args[1])
    _ecx_storage_start_touch[args.registers.esp.address.address] = (
        entity, other)


@EntityPostHook(
    EntityCondition.equals_entity_classname(ZONE_ENTITY_CLASSNAME),
    "start_touch")
def post_start_touch(args, ret_val):
    entity, other = _ecx_storage_start_touch.pop(
        args.registers.esp.address.address)

    try:
        zone_entity = zone_entities[entity.index]
    except KeyError:
        return

    try:
        player = players[other.index]
    except ValueError:
        return

    if zone_entity.zone.teleport['origin'] is not None:
        if zone_entity.zone.teleport['angles'] is not None:
            player.teleport(zone_entity.zone.teleport['origin'],
                            zone_entity.zone.teleport['angles'])
        else:
            player.teleport(zone_entity.zone.teleport['origin'])
    elif zone_entity.zone.teleport['angles'] is not None:
        player.teleport(None, zone_entity.zone.teleport['angles'])

    if zone_entity.zone.boost is not None:
        player.base_velocity = zone_entity.zone.boost

    if zone_entity.zone.nojump:
        nojump_counters[player.index] += 1

    if zone_entity.zone.noduck:
        noduck_counters[player.index] += 1

    if zone_entity.zone.speed_cap is not None:
        speed_cap_seqs[player.index].append(zone_entity.zone.speed_cap)


@EntityPreHook(
    EntityCondition.equals_entity_classname(ZONE_ENTITY_CLASSNAME),
    "end_touch")
def pre_end_touch(args):
    entity = make_object(Entity, args[0])
    other = make_object(Entity, args[1])
    _ecx_storage_end_touch[args.registers.esp.address.address] = (
        entity, other)


@EntityPostHook(
    EntityCondition.equals_entity_classname(ZONE_ENTITY_CLASSNAME),
    "end_touch")
def post_end_touch(args, ret_val):
    entity, other = _ecx_storage_end_touch.pop(
        args.registers.esp.address.address)

    try:
        zone_entity = zone_entities[entity.index]
    except KeyError:
        return

    try:
        player = players[other.index]
    except ValueError:
        return

    if zone_entity.zone.nojump:
        nojump_counters[player.index] = max(
            0, nojump_counters[player.index] - 1)

    if zone_entity.zone.noduck:
        noduck_counters[player.index] = max(
            0, noduck_counters[player.index] - 1)

    if zone_entity.zone.speed_cap is not None:
        if zone_entity.zone.speed_cap in speed_cap_seqs[player.index]:
            speed_cap_seqs[player.index].remove(zone_entity.zone.speed_cap)


@OnPlayerRunCommand
def listener_on_player_run_command(player, user_cmd):
    if nojump_counters[player.index] > 0:
        user_cmd.buttons &= ~PlayerButtons.JUMP

    if noduck_counters[player.index] > 0:
        user_cmd.buttons &= ~PlayerButtons.DUCK

    if speed_cap_seqs[player.index]:
        speed_cap = min(speed_cap_seqs[player.index])
        if 0 < speed_cap < player.velocity.length:
            new_velocity = player.velocity
            new_velocity.length = int(speed_cap)
            player.base_velocity = new_velocity - player.velocity
