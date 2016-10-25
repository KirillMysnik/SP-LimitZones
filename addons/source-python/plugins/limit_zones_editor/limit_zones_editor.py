from enum import IntEnum
import json

from colors import BLUE, GREEN, ORANGE
from commands.typed import TypedClientCommand, TypedSayCommand
from effects import box
from engines.precache import Model
from engines.server import global_vars
from filters.recipients import RecipientFilter
from listeners import OnClientDisconnect, OnLevelInit
from listeners.tick import TickRepeat
from mathlib import Vector
from menus import SimpleMenu, SimpleOption, Text
from messages import SayText2
from paths import GAME_PATH
from players.dictionary import PlayerDictionary

from advanced_ts import BaseLangStrings

from .info import info


TICK_REPEAT_INTERVAL = 0.1

EDITOR_LINE_COLOR = GREEN
EDITOR_LINE_MODEL = Model('sprites/laserbeam.vmt')
EDITOR_LINE_WIDTH = 2
EDITOR_STEP_UNITS = 8

INSPECT_LINE_COLOR = BLUE
INSPECT_LINE_MODEL = Model('sprites/laserbeam.vmt')
INSPECT_LINE_WIDTH = 2

HIGHLIGHT_LINE_COLOR = ORANGE
HIGHLIGHT_LINE_MODEL = Model('sprites/laserbeam.vmt')
HIGHLIGHT_LINE_WIDTH = 4

MAPDATA_PATH = GAME_PATH / "mapdata" / "limit_zones"

strings = BaseLangStrings(info.basename)

MSG_ERR_INVALID_COORDINATES = SayText2(strings['error invalid_coordinates'])
MSG_LZ_END_WRONG_ORDER = SayText2(strings['lz_end wrong_order'])
MSG_LZ_START_WRONG_ORDER = SayText2(strings['lz_start wrong_order'])
MSG_LZ_INSPECT_START = SayText2(strings['lz_inspect start'])
MSG_LZ_INSPECT_STOP = SayText2(strings['lz_inspect stop'])
MSG_ERR_NONE_HIGHLIGHTED = SayText2(strings['error none_highlighted'])
MSG_ERR_INVALID_ATTACH_TO_ARG = SayText2(
    strings['error invalid_attach_to_arg'])


class IncorrectEditOrder(Exception):
    pass


class InvalidCoordinates(Exception):
    pass


class HighlightChoice(IntEnum):
    HL_NEXT = 0
    HL_PREV = 1
    DELETE = 2
    TOGGLE_NOJUMP = 3
    TOGGLE_NODUCK = 4


class VectorAttachTo(IntEnum):
    VIEW_COORDINATES = 1
    PLAYER_ORIGIN = 2


players = PlayerDictionary()
popups = {}


def round_vector(vector, step):
    vector.x = step * round(vector.x / step)
    vector.y = step * round(vector.y / step)
    vector.z = step * round(vector.z / step)


def vector_to_dict(vector):
    return {
        'x': vector.x,
        'y': vector.y,
        'z': vector.z
    }


def dict_to_vector(dict_):
    return Vector(dict_['x'], dict_['y'], dict_['z'])


def vector_to_str(vector):
    return "{x:.2f} {y:.2f} {z:.2f}".format(x=vector.x, y=vector.y, z=vector.z)


class Zone:
    def __init__(self, *args):
        # From JSON-dict
        if isinstance(args[0], dict):
            dict_ = args[0]
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

        # From mins and maxs vectors
        else:
            mins, maxs = args
            properties = {
                'nojump': False,
                'noduck': False,
                'speed_cap': None,
                'teleport': {
                    'origin': None,
                    'angles': None
                },
                'boost': None,
            }

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

    def draw_inspect(self, recipients):
        box(
            recipients,
            self.mins,
            self.maxs,
            color=INSPECT_LINE_COLOR,
            life_time=TICK_REPEAT_INTERVAL,
            halo=INSPECT_LINE_MODEL,
            model=INSPECT_LINE_MODEL,
            start_width=INSPECT_LINE_WIDTH,
            end_width=INSPECT_LINE_WIDTH
        )

    def draw_highlight(self, recipients):
        box(
            recipients,
            self.mins,
            self.maxs,
            color=HIGHLIGHT_LINE_COLOR,
            life_time=TICK_REPEAT_INTERVAL,
            halo=HIGHLIGHT_LINE_MODEL,
            model=HIGHLIGHT_LINE_MODEL,
            start_width=HIGHLIGHT_LINE_WIDTH,
            end_width=HIGHLIGHT_LINE_WIDTH
        )

    @property
    def origin(self):
        return (self.mins + self.maxs) / 2

    def to_dict(self):
        dict_ = {
            'mins': vector_to_dict(self.mins),
            'maxs': vector_to_dict(self.maxs),
            'properties': {
                'nojump': self._properties['nojump'],
                'noduck': self._properties['noduck'],
                'speed_cap': self._properties['speed_cap'],
                'teleport': {
                    'origin': None,
                    'angles': None
                },
                'boost': None,
            }
        }

        if self._properties['teleport']['origin'] is not None:
            dict_['properties']['teleport']['origin'] = vector_to_dict(
                self._properties['teleport']['origin'])

        if self._properties['teleport']['angles'] is not None:
            dict_['properties']['teleport']['angles'] = vector_to_dict(
                self._properties['teleport']['angles'])

        if self._properties['boost'] is not None:
            dict_['properties']['boost'] = vector_to_dict(
                self._properties['boost'])

        return dict_


class ZonesStorage(list):
    def save_to_file(self):
        json_dict = {
            'zones': [],
        }
        for zone in self:
            json_dict['zones'].append(zone.to_dict())

        with open(self.filepath, 'w') as f:
            json.dump(json_dict, f, indent=4)

    def load_from_file(self):
        if not self.filepath.isfile():
            self.clear()
            return

        with open(self.filepath, 'r') as f:
            json_dict = json.load(f)

        for zone_json in json_dict['zones']:
            self.append(Zone(zone_json))
            highlights.append_zone()

    @property
    def filepath(self):
        return MAPDATA_PATH / "{basename}.json".format(
            basename=global_vars.map_name)

zones_storage = ZonesStorage()


class Inspects(RecipientFilter):
    def __init__(self):
        super().__init__()
        self.remove_all_players()

    def tick(self):
        for zone in zones_storage:
            zone.draw_inspect(self)

    def client_disconnect(self, index):
        self.remove_recipient(index)

inspects = Inspects()


class Highlights(list):
    def highlight_next(self, index):
        zone_id = self.get_zone_id_by_index(index)
        if zone_id is None:
            if self:
                self[0].add_recipient(index)
                return zones_storage[0]

            return None

        else:
            self[zone_id].remove_recipient(index)

            zone_id += 1
            if len(self) > zone_id:
                self[zone_id].add_recipient(index)
                return zones_storage[zone_id]

            else:
                return None

    def highlight_prev(self, index):
        zone_id = self.get_zone_id_by_index(index)
        if zone_id is None:
            if self:
                self[-1].add_recipient(index)
                return zones_storage[-1]

            return None

        else:
            self[zone_id].remove_recipient(index)

            zone_id -= 1
            if 0 <= zone_id:
                self[zone_id].add_recipient(index)
                return zones_storage[zone_id]

            else:
                return None

    def get_zone_id_by_index(self, index):
        for zone_id, recipients in enumerate(self):
            if index in recipients:
                return zone_id

        return None

    def append_zone(self):
        recipients = RecipientFilter()
        recipients.remove_all_players()
        self.append(recipients)

    def pop_zone(self, zone_id):
        self.pop(zone_id)

    def tick(self):
        for zone_id, recipients in enumerate(self):
            zones_storage[zone_id].draw_highlight(recipients)

    def client_disconnect(self, index):
        for recipients in self:
            recipients.remove_recipient(index)

highlights = Highlights()


class ZonesEdit(dict):
    def start_edit(self, index, attach_to):
        if index in self:
            raise IncorrectEditOrder(
                "You have to call end_edit on this index first")

        if attach_to == VectorAttachTo.VIEW_COORDINATES:
            start_vector = players[index].view_coordinates
        else:
            start_vector = players[index].origin

        if start_vector is None:
            raise InvalidCoordinates("Couldn't get start point")

        round_vector(start_vector, EDITOR_STEP_UNITS)

        self[index] = (attach_to, start_vector)

    def end_edit(self, index):
        try:
            attach_to, start_vector = self.pop(index)
        except KeyError:
            raise IncorrectEditOrder(
                "You have to call start_edit on this index first")

        if attach_to == VectorAttachTo.VIEW_COORDINATES:
            end_vector = players[index].view_coordinates
        else:
            end_vector = players[index].origin

        if end_vector is None:
            raise InvalidCoordinates("Couldn't get end point")

        round_vector(end_vector, EDITOR_STEP_UNITS)

        zone = Zone(start_vector, end_vector)
        zones_storage.append(zone)
        highlights.append_zone()

    def cancel_edit(self, index):
        try:
            del self[index]
        except KeyError:
            raise IncorrectEditOrder(
                "You have to call start_edit on this index first")

    def tick(self):
        for index, (attach_to, start_vector) in self.items():
            if attach_to == VectorAttachTo.VIEW_COORDINATES:
                end_vector = players[index].view_coordinates
            else:
                end_vector = players[index].origin

            if end_vector is None:
                return

            round_vector(end_vector, EDITOR_STEP_UNITS)

            box(
                RecipientFilter(index),
                start_vector,
                end_vector,
                color=EDITOR_LINE_COLOR,
                life_time=TICK_REPEAT_INTERVAL,
                halo=EDITOR_LINE_MODEL,
                model=EDITOR_LINE_MODEL,
                start_width=EDITOR_LINE_WIDTH,
                end_width=EDITOR_LINE_WIDTH
            )

zones_edit = ZonesEdit()


def send_highlight_popup(index, zone):
    if index in popups:
        popups[index].close(index)

    popup = popups[index] = SimpleMenu(
        select_callback=select_callback_highlight)

    popup.append(SimpleOption(
            choice_index=1,
            text=strings['popup highlight next_zone'],
            value=HighlightChoice.HL_NEXT
    ))

    popup.append(SimpleOption(
        choice_index=2,
        text=strings['popup highlight prev_zone'],
        value=HighlightChoice.HL_PREV
    ))

    if zone is None:
        popup.append(Text(strings['popup highlight current_zone none']))
    else:
        if zone.teleport['origin'] is None:
            teleport_origin = "- - -"
        else:
            teleport_origin = vector_to_str(zone.teleport['origin'])

        if zone.teleport['angles'] is None:
            teleport_angles = "- - -"
        else:
            teleport_angles = vector_to_str(zone.teleport['angles'])

        if zone.boost is None:
            boost = "- - -"
        else:
            boost = vector_to_str(zone.boost)

        popup.append(Text(strings['popup highlight current_zone'].tokenize(
            nojump=zone.nojump,
            noduck=zone.noduck,
            speed_cap=zone.speed_cap,
            teleport_origin=teleport_origin,
            teleport_angles=teleport_angles,
            boost=boost,
        )))

        popup.append(SimpleOption(
            choice_index=3,
            text=strings['popup highlight delete'],
            value=HighlightChoice.DELETE
        ))

        popup.append(SimpleOption(
            choice_index=4,
            text=strings['popup highlight toggle_nojump'],
            value=HighlightChoice.TOGGLE_NOJUMP
        ))

        popup.append(SimpleOption(
            choice_index=5,
            text=strings['popup highlight toggle_noduck'],
            value=HighlightChoice.TOGGLE_NODUCK
        ))

    popup.send(index)


def send_delete_popup(index):
    if index in popups:
        popups[index].close(index)

    popup = popups[index] = SimpleMenu(select_callback=select_callback_delete)
    popup.append(Text(strings['popup delete title']))
    popup.append(SimpleOption(
        choice_index=1,
        text=strings['popup delete no'],
        value=False
    ))
    popup.append(SimpleOption(
        choice_index=2,
        text=strings['popup delete yes'],
        value=True
    ))
    popup.send(index)


def select_callback_highlight(popup, index, option):
    if option.value == HighlightChoice.HL_NEXT:
        zone = highlights.highlight_next(index)
        send_highlight_popup(index, zone)
    elif option.value == HighlightChoice.HL_PREV:
        zone = highlights.highlight_prev(index)
        send_highlight_popup(index, zone)
    elif option.value == HighlightChoice.DELETE:
        send_delete_popup(index)
    elif option.value == HighlightChoice.TOGGLE_NOJUMP:
        zone = zones_storage[highlights.get_zone_id_by_index(index)]
        zone.nojump = not zone.nojump
        send_highlight_popup(index, zone)
    elif option.value == HighlightChoice.TOGGLE_NODUCK:
        zone = zones_storage[highlights.get_zone_id_by_index(index)]
        zone.noduck = not zone.noduck
        send_highlight_popup(index, zone)


def select_callback_delete(popup, index, option):
    old_zone_id = highlights.get_zone_id_by_index(index)
    if old_zone_id is None:
        return

    if option.value:
        zone = highlights.highlight_prev(index)

        highlights.pop_zone(old_zone_id)
        zones_storage.pop(old_zone_id)

    else:
        zone = zones_storage[old_zone_id]

    send_highlight_popup(index, zone)


@TypedClientCommand('lz_start', "limit_zones_editor.create")
@TypedSayCommand('!lz_start', "limit_zones_editor.create")
def typed_lz_start(command_info, attach_to_str:str="view"):
    if attach_to_str == "view":
        attach_to = VectorAttachTo.VIEW_COORDINATES
    elif attach_to_str == "origin":
        attach_to = VectorAttachTo.PLAYER_ORIGIN
    else:
        MSG_ERR_INVALID_ATTACH_TO_ARG.send(command_info.index)
        return

    try:
        zones_edit.start_edit(command_info.index, attach_to)
    except IncorrectEditOrder:
        MSG_LZ_START_WRONG_ORDER.send(command_info.index)
    except InvalidCoordinates:
        MSG_ERR_INVALID_COORDINATES.send(command_info.index)


@TypedClientCommand('lz_end', "limit_zones_editor.create")
@TypedSayCommand('!lz_end', "limit_zones_editor.create")
def typed_lz_start(command_info):
    try:
        zones_edit.end_edit(command_info.index)
    except IncorrectEditOrder:
        MSG_LZ_END_WRONG_ORDER.send(command_info.index)
    except InvalidCoordinates:
        MSG_ERR_INVALID_COORDINATES.send(command_info.index)


@TypedClientCommand('lz_cancel', "limit_zones_editor.create")
@TypedSayCommand('!lz_cancel', "limit_zones_editor.create")
def typed_lz_cancel(command_info):
    try:
        zones_edit.cancel_edit(command_info.index)
    except IncorrectEditOrder:
        MSG_LZ_END_WRONG_ORDER.send(command_info.index)


@TypedClientCommand('lz_save_to_file', "limit_zones_editor.create")
@TypedSayCommand('!lz_save_to_file', "limit_zones_editor.create")
def typed_lz_save_to_file(command_info):
    zones_storage.save_to_file()


@TypedClientCommand('lz_load_from_file', "limit_zones_editor.create")
@TypedSayCommand('!lz_load_from_file', "limit_zones_editor.create")
def typed_lz_load_from_file(command_info):
    zones_storage.load_from_file()


@TypedClientCommand('lz_inspect', "limit_zones_editor.inspect")
@TypedSayCommand('!lz_inspect', "limit_zones_editor.inspect")
def typed_lz_inspect(command_info):
    if command_info.index in inspects:
        inspects.remove_recipient(command_info.index)
        MSG_LZ_INSPECT_STOP.send(command_info.index)
    else:
        inspects.add_recipient(command_info.index)
        MSG_LZ_INSPECT_START.send(command_info.index)


@TypedClientCommand('lz_highlight', "limit_zones_editor.create")
@TypedSayCommand('!lz_highlight', "limit_zones_editor.create")
def typed_lz_highlight(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        send_highlight_popup(command_info.index, None)
    else:
        zone = zones_storage[zone_id]
        send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_set_teleport_origin', "limit_zones_editor.create")
@TypedSayCommand('!lz_set_teleport_origin', "limit_zones_editor.create")
def typed_lz_set_teleport_origin(command_info, x:float, y:float, z:float):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.teleport['origin'] = Vector(x, y, z)
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_copy_teleport_origin', "limit_zones_editor.create")
@TypedSayCommand('!lz_copy_teleport_origin', "limit_zones_editor.create")
def typed_lz_copy_teleport_origin(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.teleport['origin'] = players[command_info.index].origin
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_unset_teleport_origin', "limit_zones_editor.create")
@TypedSayCommand('!lz_unset_teleport_origin', "limit_zones_editor.create")
def typed_lz_unset_teleport_origin(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.teleport['origin'] = None
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_set_teleport_angles', "limit_zones_editor.create")
@TypedSayCommand('!lz_set_teleport_angles', "limit_zones_editor.create")
def typed_lz_set_teleport_angles(command_info, x:float, y:float, z:float):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.teleport['angles'] = Vector(x, y, z)
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_copy_teleport_angles', "limit_zones_editor.create")
@TypedSayCommand('!lz_copy_teleport_angles', "limit_zones_editor.create")
def typed_lz_copy_teleport_angles(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.teleport['angles'] = players[command_info.index].angles
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_unset_teleport_angles', "limit_zones_editor.create")
@TypedSayCommand('!lz_unset_teleport_angles', "limit_zones_editor.create")
def typed_lz_unset_teleport_angles(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.teleport['angles'] = None
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_set_speed_cap', "limit_zones_editor.create")
@TypedSayCommand('!lz_set_speed_cap', "limit_zones_editor.create")
def typed_lz_set_speed_cap(command_info, speed_cap:float):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.speed_cap = speed_cap
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_unset_speed_cap', "limit_zones_editor.create")
@TypedSayCommand('!lz_unset_speed_cap', "limit_zones_editor.create")
def typed_lz_unset_speed_cap(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.speed_cap = None
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_set_boost', "limit_zones_editor.create")
@TypedSayCommand('!lz_set_boost', "limit_zones_editor.create")
def typed_lz_set_boost(command_info, x:float, y:float, z:float):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.boost = Vector(x, y, z)
    send_highlight_popup(command_info.index, zone)


@TypedClientCommand('lz_unset_boost', "limit_zones_editor.create")
@TypedSayCommand('!lz_unset_boost', "limit_zones_editor.create")
def typed_lz_unset_boost(command_info):
    zone_id = highlights.get_zone_id_by_index(command_info.index)
    if zone_id is None:
        MSG_ERR_NONE_HIGHLIGHTED.send(command_info.index)
        return

    zone = zones_storage[zone_id]
    zone.boost = None
    send_highlight_popup(command_info.index, zone)


@OnClientDisconnect
def listener_on_client_disconnect(index):
    zones_edit.pop(index, None)
    inspects.client_disconnect(index)
    highlights.client_disconnect(index)

    popups.pop(index, None)


@TickRepeat
def tick_repeat():
    zones_edit.tick()
    inspects.tick()
    highlights.tick()

tick_repeat.start(TICK_REPEAT_INTERVAL, limit=0)


@OnLevelInit
def listener_on_level_init(level_name):
    popups.clear()
    players.clear()
