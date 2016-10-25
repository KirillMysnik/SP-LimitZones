from cvars.public import PublicConVar
from plugins.info import PluginInfo


info = PluginInfo()
info.name = "LimitZones"
info.basename = 'limit_zones'
info.author = 'Kirill "iPlayer" Mysnik'
info.version = '1.0'
info.variable = '{}_version'.format(info.basename)
info.convar = PublicConVar(
    info.variable, info.version, "{} version".format(info.name))

info.url = "https://github.com/KirillMysnik/SP-LimitZones"
