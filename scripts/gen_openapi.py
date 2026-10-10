#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate OpenAPI 3.0 YAML for 网易智造 App API from decompiled Retrofit interfaces."""
import os
import yaml

# ---- type helpers ----
def ref(name): return ("ref", name)
def arr(elem): return ("array", elem)
STR="string"; INT="integer"; I64="int64"; BOOL="boolean"; NUM="number"; OBJ="object"

def prop(t, desc=None):
    if isinstance(t, str):
        m = {"type": t}
        if t == "int64": m = {"type": "integer", "format": "int64"}
        if t == "object": m = {}
    elif t[0] == "ref":
        m = {"$ref": "#/components/schemas/" + t[1]}
    elif t[0] == "array":
        m = {"type": "array", "items": prop(t[1])}
    else:
        m = {}
    if desc: m["description"] = desc
    return m

def schema(props):
    return {"type": "object", "properties": {k: prop(v) for k, v in props.items()}}

# ================= SCHEMAS =================
S = {}

S["PageInfo"] = schema({
    "pageCnt": INT, "pageIndex": INT, "pageSize": INT, "totalCnt": INT})

S["FlyAlertItem"] = schema({
    "isCloseOuterWhenClick": BOOL, "isCloseWhenCancel": BOOL, "isCloseWhenSubmit": BOOL,
    "isShowClose": BOOL, "alertContent": STR, "alertContentAlign": INT, "cancelTextColor": INT,
    "alertCode": INT, "okCountDown": INT, "okTextColor": INT, "permissions": arr(STR),
    "statistics": OBJ, "alertImageUrl": STR, "alertTitle": STR, "cancelStatisticsKey": STR,
    "cancelText": STR, "cancelUrl": STR, "closeStatisticsKey": STR, "okStatisticsKey": STR,
    "okText": STR, "okUrl": STR, "pageUrl": STR, "showStatisticsKey": STR, "successUrl": STR})

S["ServerNotice"] = schema({"id": STR, "title": STR, "url": STR})
S["UrsTokenResponse"] = schema({"retCode": INT, "result": STR, "retDesc": STR})
S["UserInfo"] = schema({"sex": INT, "welcomeFlg": INT, "birthday": I64, "pid": I64,
    "accountDesc": STR, "accountType": STR, "nickname": STR, "thumbnails": STR, "uid": STR})
S["WeixinTokenResponse"] = schema({"access_token": STR, "openid": STR, "refresh_token": STR})
S["Command"] = schema({"type": INT, "code": STR})
S["SmartOption"] = schema({"code": INT, "desc": STR})
S["WifiConfig"] = schema({"mode": arr(STR), "useProductSign": BOOL, "port": INT,
    "showInitStatusTime": I64, "confirmButtonText": STR, "helpBtnTxt": STR, "helpClickUrl": STR,
    "helpImg": STR, "host": STR, "ssidDesc": STR, "ssidPattern": STR, "wifiGuideImgAn": STR,
    "wifiGuidePage": STR})
S["ProductDetail"] = schema({"productDesc": STR, "productImgUrl": STR, "productName": STR,
    "productOrderUrl": STR})
S["Product"] = schema({"available": BOOL, "bindConfig": ref("ProductDetail"), "connectMode": INT,
    "devType": INT, "id": INT, "vender": INT, "viewType": INT, "commands": arr(ref("Command")),
    "smartOptions": arr(ref("SmartOption")), "config": OBJ, "venderConfig": OBJ,
    "bleConfig": STR, "displayName": STR, "imageUrl": STR, "model": STR, "name": STR,
    "platformProductKey": STR, "productSign": STR, "type": STR, "wapUrl": STR,
    "wifiConfig": STR, "wifiConfigModel": ref("WifiConfig")})
S["EquipStatus_Presenter"] = schema({"status": STR, "id": STR})
S["Equip"] = schema({"devType": INT, "bindType": INT, "productId": INT, "status": INT,
    "vender": INT, "weight": INT, "account": I64, "createTime": I64, "familyId": I64,
    "lastEndTime": I64, "lastStartTime": I64, "rid": I64, "roomId": I64, "updateTime": I64,
    "alias": STR, "bluetoothMacAddr": STR, "continued": STR, "dialogOks": STR,
    "manufactorId": STR, "model": STR, "name": STR, "roomName": STR, "sn": STR, "type": STR,
    "wapUrl": STR, "wifiMacAddr": STR, "isDeleted": BOOL})
S["EquipData"] = schema({"sync": BOOL, "createTime": I64, "primaryId": I64, "updateTime": I64,
    "equipType": STR, "equipUserId": STR, "result": STR, "userProfileId": STR, "isDeleted": BOOL})
S["EquipUser"] = schema({"createTime": I64, "primaryId": I64, "syncTime": I64, "updateTime": I64,
    "equipId": STR, "equipUserId": STR, "ext": STR, "userProfileId": STR, "isDeleted": BOOL})
S["EnvInfo"] = schema({"roomId": I64, "roomName": STR, "statusText": STR, "familyId": I64})
S["FamilyEnv"] = schema({"list": arr(ref("EnvInfo")), "familyId": I64})
S["FamilyEquip"] = schema({"equipInfo": ref("Equip"), "familyId": I64, "id": I64,
    "roomId": I64, "equipId": STR})
S["Room"] = schema({"icon": INT, "familyEquipList": arr(ref("FamilyEquip")), "createTime": I64,
    "familyId": I64, "id": I64, "name": STR})
S["Member"] = schema({"type": INT, "familyId": I64, "inviteTime": I64, "pid": I64,
    "headPic": STR, "name": STR, "uid": STR})
S["Family"] = schema({"id": I64, "name": STR, "ownerPid": INT, "type": INT, "theme": INT,
    "roomList": arr(ref("Room")), "memberList": arr(ref("Member")),
    "shareEquipList": arr(ref("Equip"))})
S["FamilyInfo"] = schema({"familyList": arr(ref("Family")), "sortInfo": STR, "unread": INT})
S["UserProfile"] = schema({"id": STR, "rid": I64, "name": STR, "userType": INT, "gender": INT,
    "birthday": I64, "weight": INT, "targetWeight": INT, "height": INT, "createTime": I64,
    "updateTime": I64, "avatar": STR, "isDeleted": BOOL})
S["SceneSummary"] = schema({"sceneId": I64, "sceneSubId": I64, "sceneMode": ref("SceneMode"),
    "sceneSubStatus": ref("SceneSubStatus"), "imgUrl": STR, "title": STR})
S["SceneMode"] = schema({"value": STR})
S["SceneSubStatus"] = schema({"value": STR})
S["SceneSubTmpl"] = schema({"sceneSubTmplId": I64, "bgCol": STR, "btnCol": STR, "iconUrl": STR,
    "title": STR, "titleCol": STR})
S["SceneTmpl"] = schema({"sceneSubTmplList": arr(ref("SceneSubTmpl")), "sceneTmplId": I64,
    "sceneMode": ref("SceneMode"), "desc": STR, "detailImgUrl": STR, "summaryImgUrl": STR,
    "title": STR})
S["SceneHomepageRsp"] = schema({"manualList": arr(ref("SceneSummary")),
    "autoTmplList": arr(ref("SceneTmpl"))})
S["SceneResult"] = schema({"logId": I64})
S["OperationStatus"] = schema({"code": STR, "value": OBJ})
S["EquipStatus_Entity"] = schema({"onlineStatus": INT, "statusList": arr(ref("OperationStatus")),
    "equipId": STR, "statusText": STR})
S["EquipStatusResponse"] = schema({"status": INT})
S["EquipVerifyResponse"] = schema({"isAllow": BOOL, "isMine": BOOL, "nickname": STR})
S["InviteUnreadRsp"] = schema({"inviteUnread": INT})
S["OtaInfo"] = schema({"content": STR, "title": STR})

# Sweeper
S["CleanScheme"] = schema({"isRunning": BOOL, "isSelected": BOOL,
    "roomSettings": arr(ref("RoomCleanScheme")), "cleanSchemeId": I64, "cleanMode": INT,
    "mapId": I64, "equipId": STR})
S["RoomCleanScheme"] = schema({"roomId": INT, "repeatClean": INT, "waterLevel": INT, "windPower": INT})
S["CleanSchemeRsp"] = schema({"total": INT, "list": arr(ref("CleanScheme"))})
S["DeviceCtrlInfo"] = schema({"rscode": INT})
S["HistoryMap"] = schema({"mapType": INT, "createTime": I64, "mapId": I64, "mapImgUrl": STR})
S["LoadingInfo"] = schema({"tips": arr(STR)})
S["MemoryMap"] = schema({"mapId": I64, "mapImgUrl": STR, "mapName": STR, "mapUrl": STR})
S["MemoryMaps"] = schema({"mapList": arr(ref("MemoryMap")), "currentMapId": I64})
S["ConsumableInfo"] = schema({"totalTime": INT, "usedTime": INT})
S["SweeperConsumableData"] = schema({"dishcloth": ref("ConsumableInfo"),
    "filterNet": ref("ConsumableInfo"), "mainBrush": ref("ConsumableInfo"),
    "sideBrush": ref("ConsumableInfo"), "totalTime": INT, "usedTime": INT})
S["SweeperDeviceData"] = schema({"areaCleanFlag": INT, "isOnline": BOOL, "isOTAUpdating": BOOL,
    "isRoomCleaningStatus": BOOL, "chargeStatus": INT, "battery": INT, "cleanSize": INT,
    "cleanTime": INT, "faultCode": INT, "faultType": INT, "todayCleanSize": INT,
    "todayCleanTime": INT, "cleanSchemeId": I64, "mapId": I64, "mapType": INT,
    "repeatClean": INT, "mapUrl": STR, "protocolVersion": STR, "waterControl": INT,
    "windPower": INT, "workMode": STR})
S["SweeperFirmwareInfo"] = schema({"firmwareVersion": STR})
S["SweeperLogData"] = schema({"cleanArea": INT, "cleanTime": INT, "cleanType": STR, "faultType": STR,
    "startTime": I64, "id": STR, "mapName": STR, "mapUrl": STR})
S["SweeperMapEditResponse"] = schema({"rscode": INT})
S["SweeperPendingMap"] = schema({"mapType": INT, "mapId": I64, "equipId": STR, "mapImgUrl": STR,
    "mapUrl": STR})
S["SweeperSchedule"] = schema({"cleanMode": INT, "cleanSchemeId": I64, "dayTime": INT,
    "enable": INT, "mapId": I64, "orderId": INT, "repeat": INT, "repeatClean": INT,
    "rooms": arr(INT), "roomsName": arr(STR), "waterControl": INT, "weekday": INT, "windPower": INT})
S["SweeperScheduleData"] = schema({"dayTime": INT, "enable": INT, "orderCount": INT,
    "orderId": INT, "repeat": INT, "repeatClean": INT, "rooms": arr(INT), "waterControl": INT,
    "weekday": INT, "windPower": INT, "orderList": arr(ref("SweeperSchedule")),
    "cleanSchemeId": I64, "mapId": I64, "cleanMode": INT, "roomsName": arr(STR)})
S["SweeperSettingData"] = schema({"brokenEnable": INT, "carpetTurbo": INT, "historyMap": INT,
    "quietBeginTime": INT, "quietEndTime": INT, "quietMode": INT, "repeatClean": INT,
    "timeSec": INT, "timeZone": INT, "voiceEnable": INT, "volume": INT, "waterControl": INT,
    "windPower": INT, "firmwareVersion": STR})
S["SetSchemeReq"] = schema({"cleanSchemeId": I64, "mapId": I64, "equipId": STR})
S["TrapMapRsp"] = schema({"url": STR})
S["RoomInfo"] = schema({"roomId": INT, "roomName": STR})
S["MapMask"] = schema({"value": INT})
S["AreaPoint"] = schema({"pointX": STR, "pointY": STR})
S["AreaFrame"] = schema({"id": INT, "type": INT, "pointList": arr(ref("AreaPoint"))})
S["VirtualWallFrame"] = schema({"id": INT, "type": INT, "pointList": arr(ref("AreaPoint"))})
S["SweeperPushMap"] = schema({"equipId": STR, "productId": INT, "mapId": I64, "mapType": INT, "mapUrl": STR})
S["SweeperPushInfo"] = schema({"areaCleanFlag": INT, "chargeStatus": INT, "cleanSchemeId": I64,
    "equipId": STR, "battery": INT, "cleanSize": INT, "cleanTime": INT, "faultCode": INT,
    "faultType": INT, "productId": INT, "mapId": I64, "repeatClean": INT, "waterControl": INT,
    "windPower": INT, "workMode": STR})
S["SweeperOtaStatus"] = schema({"isOta": BOOL})

# Firmware
S["CheckUpdateReport"] = schema({"releaseTime": I64, "totalLength": I64, "version": STR,
    "information": STR, "url": STR, "sign": STR})
S["CheckUpdateResponse"] = schema({"isLatest": BOOL, "report": ref("CheckUpdateReport"),
    "releaseTime": I64, "totalLength": I64, "information": STR, "message": STR, "sign": STR,
    "title": STR, "url": STR, "version": STR})
S["OtaResponse"] = schema({"mcuStatus": INT})

# Host
S["UserAccount"] = schema({"deregistered": BOOL, "pid": INT, "avatar": STR, "nickname": STR,
    "username": STR})
S["ShareEquipRequestModel"] = schema({"read": BOOL, "productId": INT, "status": INT, "id": I64,
    "alias": STR, "equipId": STR, "imageUrl": STR, "name": STR, "sn": STR,
    "owner": ref("UserAccount"), "shared": ref("UserAccount")})
S["ShareEquipRequestResponse"] = schema({"list": arr(ref("ShareEquipRequestModel"))})
S["ShareEquipModel"] = schema({"productId": INT, "sharedNum": INT, "alias": STR, "id": STR,
    "imageUrl": STR, "name": STR, "sn": STR})
S["ShareEquipResponse"] = schema({"list": arr(ref("ShareEquipModel")), "recommendUrl": STR})
S["SharedUserAccountModel"] = schema({"status": INT, "acceptTime": I64, "shareRequestId": I64,
    "shareTime": I64, "shared": ref("UserAccount")})
S["UpdateCheckResponse_Host"] = schema({"force": BOOL, "length": I64, "desc": STR, "title": STR,
    "url": STR, "version": STR})
S["UpdateCheckRequest"] = schema({"cver": INT, "sdk": INT, "p": STR, "source": STR})
S["UserGlobalInfo"] = schema({"agreementInfo": OBJ, "read": BOOL, "agreementId": INT,
    "privatePolicyId": INT, "content": STR, "title": STR})

# Tuya
S["TuyaUserInfo"] = schema({"tuyaHomeId": I64, "tuyaTk": STR})

# ---- ResponseWrapper generic + typed wrappers ----
S["ResponseWrapper"] = schema({
    "code": INT, "errorMsg": STR, "result": OBJ, "showType": INT,
    "alertInfo": ref("FlyAlertItem"), "rawResult": OBJ})
S["ListResponse"] = schema({"list": arr(OBJ), "page": ref("PageInfo")})

def wrapper_schema(result_prop):
    d = {"code": prop(INT), "errorMsg": prop(STR), "result": result_prop,
         "showType": prop(INT), "alertInfo": prop(("ref","FlyAlertItem")), "rawResult": prop(OBJ)}
    return {"type": "object", "properties": d}

def listresponse_schema(elem_prop):
    return {"type": "object",
            "properties": {"list": {"type": "array", "items": elem_prop},
                           "page": {"$ref": "#/components/schemas/PageInfo"}}}

# ================= ENDPOINTS =================
# result notations: ("obj",) | ("ref",NAME) | ("list",ELEM) | ("int",) | ("str",)
OBJ_R=("obj",); INT_R=("int",)
def REF_R(n): return ("ref", n)
def LIST_R(e): return ("list", e)

# param: (name, type, required, desc)   type in {string,integer,int64,boolean}
# body: None | ("form", [(name,type,req,desc)]) | ("json", schema_name_or_None)
EP = []

def add(tag, method, path, opId, summary, params, body, result):
    EP.append(dict(tag=tag, method=method, path=path, opId=opId, summary=summary,
                   params=params, body=body, result=result))

K="kernel"; SW="sweeper"; FW="firmware"; HO="host"; TU="tuya"; EX="misc"

# ---- Kernel ----
add(K,"post","/ai-app/equip/checkUpdate","checkUpdate","检查设备更新",[],("form",[("_params",STR,False,"任意键值对 Map<String,String>")]),OBJ_R)
add(K,"post","/ai-app/data/add","dataAdd","新增数据",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"post","/ai-app/data/delete","dataDel","删除数据",[],("form",[("dataId",STR,True,"数据ID"),("equipUserId",STR,True,"设备用户ID"),("userProfileId",STR,True,"用户档案ID")]),OBJ_R)
add(K,"get","/ai-app/data/listall","dataListAll","查询全部数据",[("fromTime","int64",True,"起始时间")],None,LIST_R("EquipData"))
add(K,"post","/ai-app/data/update","dataUpdate","更新数据",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"post","/ai-app/user/agreement/deal","dealNewestAgreement","处理最新协议",[],("form",[("agreementId","integer",False,"协议ID，默认-1"),("privatePolicyId","integer",False,"隐私政策ID，默认-1")]),OBJ_R)
add(K,"post","/ai-app/equip/bind","equipBind","绑定设备",[],("form",[("_params",STR,False,"任意键值对")]),REF_R("Equip"))
add(K,"get","/ai-app/equip/list","equipList","设备列表",[],None,LIST_R("Equip"))
add(K,"get","/ai-app/equip/resetFactory","equipReset","恢复出厂",[("equipId",STR,True,"设备ID")],None,OBJ_R)
add(K,"post","/ai-app/equip/sort","equipSort","设备排序",[],("form",[("equipIdList",STR,True,"设备ID列表(List)")]),OBJ_R)
add(K,"get","/ai-app/equip/status","equipStatus","设备状态",[("productId","integer",True,"产品ID"),("sn",STR,True,"序列号")],None,REF_R("EquipStatusResponse"))
add(K,"post","/ai-app/equip/unbind","equipUnBind","解绑设备",[],("form",[("equipId",STR,True,"设备ID")]),OBJ_R)
add(K,"post","/ai-app/equip/update","equipUpdate","更新设备",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"post","/ai-app/equip_user/add","equipUserAdd","新增设备用户",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"post","/ai-app/equip_user/delete","equipUserDel","删除设备用户",[],("form",[("equipUserId",STR,True,"设备用户ID"),("equipId",STR,True,"设备ID"),("userProfileId",STR,True,"用户档案ID")]),OBJ_R)
add(K,"get","/ai-app/equip_user/list","equipUserList","设备用户列表",[],None,LIST_R("EquipUser"))
add(K,"post","/ai-app/equip_user/update","equipUserUpdate","更新设备用户",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"get","/ai-app/equip/verify","equipVerify","验证设备",[("_query",STR,False,"任意查询参数 Map")],None,REF_R("EquipVerifyResponse"))
add(K,"get","/ai-app/smart/home/{familyId}","fetchSceneHomepage","场景主页",[("familyId","int64",True,"家庭ID",True)],None,REF_R("SceneHomepageRsp"))
add(K,"get","/ai-app/account/info","getAccountInfo","账号信息",[("from","integer",False,"来源，0=免登录/1=登录后")],None,REF_R("UserInfo"))
add(K,"get","/ai-app/family/env/info/homepage","getEnvInfo","家庭环境信息",[("familyId","int64",True,"家庭ID")],None,REF_R("FamilyEnv"))
add(K,"get","/ai-app/equip/quick/getStatus","getEquipQuickStatus","快速获取设备状态",[],None,LIST_R("EquipStatus_Entity"))
add(K,"get","/ai-app/family/query","getFamily","查询家庭",[("familyId","int64",True,"家庭ID")],None,REF_R("Family"))
add(K,"get","/ai-app/family/info","getFamilyInfo","获取家庭列表信息",[],None,REF_R("FamilyInfo"))
add(K,"get","/ai-app/ota/more","getOtaInfo","OTA信息",[("productId","integer",True,"产品ID"),("version",STR,True,"版本"),("type",STR,True,"类型")],None,REF_R("OtaInfo"))
add(K,"get","/nit-anncmnt/getAnncmntInfo","getServerNotice","获取公告",[("anncmntId",STR,True,"公告ID")],None,REF_R("ServerNotice"))
add(K,"get","/ai-app/equip/v2/checkUnbind","getUnbindAlertInfo","解绑确认弹窗信息",[("equipId",STR,True,"设备ID")],None,REF_R("FlyAlertItem"))
add(K,"post","/ai-app/family/sort/info","postFamilySortInfo","家庭排序信息",[],("json",None),OBJ_R)
add(K,"get","/ai-app/product/list","productList","产品列表",[],None,LIST_R("Product"))
add(K,"get","/ai-app/app/event/view","sendEvent","事件上报",[("pushId",STR,False,"推送ID"),("productId","integer",False,"产品ID"),("eventType","integer",False,"事件类型"),("equipId",STR,False,"设备ID")],None,OBJ_R)
add(K,"post","/ai-app/smart/scene-sub/start/{familyId}/{sceneSubId}","startScene","启动场景",[("familyId","int64",True,"家庭ID",True),("sceneSubId","int64",True,"子场景ID",True)],None,REF_R("SceneResult"))
add(K,"post","/ai-app/ota/sync","syncDevice","同步设备OTA",[],("form",[("productId","integer",True,"产品ID"),("version",STR,True,"版本"),("type",STR,True,"类型"),("sn",STR,True,"序列号")]),REF_R("OtaInfo"))
add(K,"get","/ai-app/family/invite/unread","unreadInviteMsgCnt","未读邀请数",[],None,REF_R("InviteUnreadRsp"))
add(K,"get","/ai-app/equip/share/request/unread","unreadShareMsgCnt","未读分享消息数",[],None,INT_R)
add(K,"post","/ai-app/account/update","updateAccountInfo","更新账号信息",[],("form",[("nickname",STR,False,"昵称"),("sex","integer",False,"性别"),("birthday","int64",False,"生日")]),OBJ_R)
add(EX,"get","http://reg.163.com/outerLogin/oauth2/exchageMobLoginToken.do","ursToken","URS 换 token",[("id",STR,True,"NEConfig id"),("params",STR,True,"AES加密参数")],None,REF_R("UrsTokenResponse"))
add(K,"post","/ai-app/user/add","userAdd","新增用户",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"delete","/ai-app/account/deregister","userDeRegister","注销账号",[],None,OBJ_R)
add(K,"post","/ai-app/user/delete","userDel","删除用户",[],("form",[("userProfileId",STR,True,"用户档案ID")]),OBJ_R)
add(K,"get","/ai-app/user/list","userList","用户列表",[],None,LIST_R("UserProfile"))
add(K,"post","/ai-app/user/update","userUpdate","更新用户",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(K,"get","/ai-app/weixin/wx_token","weixinToken","微信token",[("code",STR,True,"微信授权code")],None,REF_R("WeixinTokenResponse"))

# ---- Sweeper ----
add(SW,"post","/ai-app/sweeper/rv03/clean-scheme","addCleanScheme","新增清扫方案",[],("json","CleanScheme"),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/addMemoryMap","addMemoryMap","保存记忆地图",[],("form",[("equipId",STR,True,"设备ID"),("historyMapId","int64",True,"历史地图ID"),("memoryMapId","int64",True,"记忆地图ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/confirmMapMsgBox","confirmMapMsgBox","确认地图弹窗",[],("form",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID"),("mapType","integer",True,"地图类型")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/deleteCleanLog","deleteCleanLog","删除清扫日志",[],("form",[("equipId",STR,True,"设备ID"),("logId",STR,True,"日志ID")]),OBJ_R)
add(SW,"delete","/ai-app/sweeper/rv03/clean-scheme","deleteCleanScheme","删除清扫方案",[("equipId",STR,True,"设备ID"),("cleanSchemeId","int64",True,"清扫方案ID"),("mapId","int64",True,"地图ID")],None,OBJ_R)
add(SW,"delete","/ai-app/sweeper/rv02/deleteMemoryMap","deleteMemoryMap","删除记忆地图",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID")],None,OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/deleteOrder","deleteOrder","删除预约",[],("form",[("equipId",STR,True,"设备ID"),("orderId","integer",True,"预约ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/deviceCtrl","deviceCtrl","设备控制",[],("form",[("equipId",STR,True,"设备ID"),("ctrltype","integer",True,"控制类型"),("value","integer",False,"值，默认1")]),REF_R("DeviceCtrlInfo"))
add(SW,"post","/ai-app/sweeper/rv02/errorReport","errorReport","错误上报",[],("form",[("equipId",STR,True,"设备ID"),("errorTypes",STR,True,"错误类型")]),OBJ_R)
add(SW,"get","/ai-app/sweeper/rv02/getCleanLogDetail","getCleanLogDetail","清扫日志详情",[("equipId",STR,True,"设备ID"),("logId",STR,True,"日志ID")],None,REF_R("SweeperLogData"))
add(SW,"get","/ai-app/sweeper/rv03/clean-scheme","getCleanScheme","查询清扫方案",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID")],None,REF_R("CleanSchemeRsp"))
add(SW,"get","/ai-app/sweeper/rv02/getItemsInfo","getConsumableInfo","耗材信息",[("equipId",STR,True,"设备ID")],None,REF_R("SweeperConsumableData"))
add(SW,"get","/ai-app/sweeper/rv02/getFirmwareInfo","getFirmwareInfo","固件信息",[("equipId",STR,True,"设备ID")],None,REF_R("SweeperFirmwareInfo"))
add(SW,"get","/ai-app/sweeper/rv02/getHistoryMaps","getHistoryMaps","历史地图列表",[("equipId",STR,True,"设备ID")],None,LIST_R("HistoryMap"))
add(SW,"get","/ai-app/sweeper/rv02/getLoadingTips","getLoadingTips","加载提示",[],None,REF_R("LoadingInfo"))
add(SW,"get","/ai-app/sweeper/rv02/getMap","getMap","获取地图",[("equipId",STR,True,"设备ID"),("mask","integer",True,"掩码"),("mapId","int64",True,"地图ID")],None,OBJ_R)
add(SW,"get","/ai-app/sweeper/rv02/getMemoryMap","getMemoryMap","记忆地图",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID")],None,REF_R("MemoryMap"))
add(SW,"get","/ai-app/sweeper/rv02/getMemoryMaps","getMemoryMaps","记忆地图列表",[("equipId",STR,True,"设备ID")],None,REF_R("MemoryMaps"))
add(SW,"get","/ai-app/sweeper/rv02/getOrderSettings","getOrderSetting","预约设置",[("equipId",STR,True,"设备ID")],None,REF_R("SweeperScheduleData"))
add(SW,"get","/ai-app/sweeper/rv02/getPendingMap","getPendingMap","待处理地图",[("equipId",STR,True,"设备ID")],None,REF_R("SweeperPendingMap"))
add(SW,"get","/ai-app/sweeper/rv02/getDeviceData","getSweeperData","扫地机数据",[("equipId",STR,True,"设备ID")],None,REF_R("SweeperDeviceData"))
add(SW,"get","/ai-app/sweeper/rv02/getSettings","getSweeperSetting","扫地机设置",[("equipId",STR,True,"设备ID")],None,REF_R("SweeperSettingData"))
add(SW,"get","/ai-app/sweeper/rv03/trap-map","getTrapMap","陷阱地图",[("equipId",STR,True,"设备ID")],None,REF_R("TrapMapRsp"))
add(SW,"post","/ai-app/sweeper/rv02/mergeMap","mergeRoom","合并房间",[],("form",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID"),("rooms",STR,True,"房间")]),REF_R("SweeperMapEditResponse"))
add(SW,"post","/ai-app/sweeper/rv02/setArea","setArea","设置区域",[],("form",[("equipId",STR,True,"设备ID"),("areaCount","integer",True,"区域数"),("areaList",STR,True,"区域列表"),("mapId","int64",True,"地图ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setPreference","setCleanPreference","清扫偏好",[],("form",[("equipId",STR,True,"设备ID"),("ctrltype","integer",True,"控制类型"),("value","integer",True,"值")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv03/set-clean-scheme","setCleanScheme","设置清扫方案",[],("json","SetSchemeReq"),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setCurrentMap","setCurrentMap","设置当前地图",[],("form",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setMapInfo","setMapInfo","设置地图信息",[],("form",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID"),("mapName",STR,False,"地图名"),("roomInfo",STR,False,"房间信息")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setNavigation","setNavigation","设置导航",[],("form",[("equipId",STR,True,"设备ID"),("ctrlValue","integer",True,"控制值"),("pointX","number",True,"X坐标"),("pointY","number",True,"Y坐标"),("mapId","int64",True,"地图ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setOrder","setOrder","设置预约",[],("form",[
    ("equipId",STR,True,"设备ID"),("enable","integer",True,"启用"),("repeat","integer",True,"重复"),
    ("orderId","integer",True,"预约ID"),("weekday","integer",True,"星期"),("daytime","integer",True,"时间"),
    ("cleanMode","integer",True,"清扫模式"),("windPower","integer",True,"风力"),("waterControl","integer",True,"水量"),
    ("repeatClean","integer",True,"重复清扫"),("mapId","int64",True,"地图ID"),("rooms",STR,True,"房间"),
    ("roomsName",STR,True,"房间名"),("cleanSchemeId","int64",True,"清扫方案ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setQuietTime","setQuietTime","设置免打扰",[],("form",[("equipId",STR,True,"设备ID"),("isOpen","integer",True,"开启"),("beginTime","integer",True,"开始时间"),("endTime","integer",True,"结束时间")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setRoomsClean","setRoomsClean","房间清扫",[],("form",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID"),("cleanType","integer",True,"清扫类型"),("ctrlValue","integer",True,"控制值"),("roomsNum","integer",True,"房间数"),("rooms",STR,True,"房间")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setTimeZone","setTimeZone","设置时区",[],("form",[("equipId",STR,True,"设备ID"),("timeZone","integer",True,"时区")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setVirtualWall","setVirtualWall","设置虚拟墙",[],("form",[("equipId",STR,True,"设备ID"),("virwallCount","integer",True,"虚拟墙数"),("virwallList",STR,True,"虚拟墙列表"),("mapId","int64",True,"地图ID")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setVoice","setVoice","设置语音",[],("form",[("equipId",STR,True,"设备ID"),("voiceEnable","integer",True,"语音开关"),("volume","integer",True,"音量")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/setWorkMode","setWorkMode","设置工作模式",[],("form",[("equipId",STR,True,"设备ID"),("ctrltype","integer",True,"控制类型"),("value","integer",True,"值")]),OBJ_R)
add(SW,"post","/ai-app/sweeper/rv02/splitMap","splitRoom","分割房间",[],("form",[("equipId",STR,True,"设备ID"),("mapId","int64",True,"地图ID"),("roomId","integer",True,"房间ID"),("pointList",STR,True,"点列表")]),REF_R("SweeperMapEditResponse"))

# ---- Firmware ----
add(FW,"get","/ai-app/ota/status","checkOtaStatus","OTA状态",[("productId","integer",True,"产品ID"),("sn",STR,True,"序列号")],None,REF_R("OtaResponse"))
add(FW,"get","/ai-app/ota/check","checkUpdate","检查更新",[("productId","integer",True,"产品ID"),("version",STR,True,"版本"),("type",STR,True,"类型"),("sn",STR,True,"序列号")],None,REF_R("CheckUpdateResponse"))

# ---- Host ----
add(HO,"post","/ai-app/equip/share/request/accept","acceptRequest","接受分享请求",[],("form",[("_params",STR,False,"任意键值对")]),REF_R("ShareEquipRequestModel"))
add(HO,"post","/ai-app/equip/share/request/add","addShareAccount","新增分享账号",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(HO,"get","/down/appver.do","appver","版本更新",[("_query",STR,False,"任意查询参数 Map")],None,REF_R("UpdateCheckResponse_Host"))
add(HO,"post","/ai-app/equip/share/request/cancel","cancelShareEquip","取消分享",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(HO,"post","/ai-app/user/agreement/deal","dealAgreement","处理协议",[],("form",[("agreementId","integer",True,"协议ID"),("privatePolicyId","integer",True,"隐私政策ID")]),OBJ_R)
add(HO,"get","/ai-app/equip/share/account","equipAcceptedUserList","已接受用户列表",[("id",STR,True,"设备ID")],None,LIST_R("SharedUserAccountModel"))
add(HO,"get","/ai-app/product/setupInfo/get","getProductDetail","产品详情",[("id","integer",True,"产品ID")],None,REF_R("ProductDetail"))
add(HO,"get","/ai-app/user/global","getUserGlobal","用户全局信息",[],None,REF_R("UserGlobalInfo"))
add(HO,"post","/ai-app/equip/share/owner/cancel","ownerCancelShareEquip","主人取消分享",[],("form",[("_params",STR,False,"任意键值对")]),OBJ_R)
add(HO,"get","/ai-app/user/account/search","queryUserAccount","搜索用户账号",[("username",STR,True,"用户名")],None,REF_R("UserAccount"))
add(HO,"post","/ai-app/equip/quick/sendCommand","quickSendCommand","快速下发命令",[],("form",[("_params",STR,False,"任意键值对 Map<String,Object>")]),OBJ_R)
add(HO,"get","/ai-app/equip/share/account/recent","recentAddUserList","最近添加用户",[],None,LIST_R("UserAccount"))
add(HO,"get","/channel/app/addLoginInfo.do","sendStatic","登录信息上报",[("cid",STR,True,"渠道ID")],None,OBJ_R)
add(HO,"get","/ai-app/equip/share/list","shareEquipList","分享设备列表",[],None,REF_R("ShareEquipResponse"))
add(HO,"get","/ai-app/equip/share/request","shareEquipRequest","分享请求",[],None,REF_R("ShareEquipRequestResponse"))
add(HO,"get","/ai-app/equip/share/request/unread","unReadMsgNum","未读消息数",[],None,INT_R)

# ---- Tuya ----
add(TU,"get","/ai-app/user/tuya/info","tuyaUserInfo","涂鸦用户信息",[],None,REF_R("TuyaUserInfo"))
add(TU,"post","/ai-app/user/tuya/log","tuyaUserLog","涂鸦日志上报",[],("form",[("errorCode",STR,False,"错误码"),("errorMsg",STR,False,"错误信息")]),OBJ_R)
add(TU,"post","/ai-app/user/tuya/homeId","uploadTuyaHomeId","上传涂鸦homeId",[],("form",[("homeId","int64",True,"homeId")]),OBJ_R)

# ---- misc hardcoded ----
add(EX,"post","/ai-app/account/uploadThumb","updateAccountAvatar","上传头像",[],("form",[("file",STR,True,"图片文件")]),OBJ_R)
add(EX,"get","/ai-app/account/headpic","accountHeadpic","头像图片",[("userProfileId",STR,True,"用户档案ID")],None,OBJ_R)

# ================= BUILD OpenAPI =================
TAGDESC = {
    "kernel": "核心业务（设备/家庭/用户/账号/场景/OTA）",
    "sweeper": "扫地机器人",
    "firmware": "固件 OTA",
    "host": "设备分享",
    "tuya": "涂鸦 Hybrid",
    "misc": "其他（登录/头像）",
}

paths = {}
for e in EP:
    p = e["path"]
    if p not in paths: paths[p] = {}
    params = []
    for q in e["params"]:
        name, typ, req, desc = q[0], q[1], q[2], q[3]
        is_path = len(q) > 4 and q[4]
        loc = "path" if is_path else "query"
        sch = {"type": "string"} if typ=="string" else \
              ({"type":"integer","format":"int64"} if typ=="int64" else {"type":"integer"})
        params.append({"name": name, "in": loc, "required": req,
                       "schema": sch, "description": desc})
    reqbody = None
    if e["body"]:
        kind, data = e["body"]
        if kind == "form":
            props = {}
            req_fields = []
            for f in data:
                fn, ft, freq, fdesc = f
                psch = {"type":"string"} if ft=="string" else \
                       ({"type":"integer","format":"int64"} if ft=="int64" else \
                        ({"type":"number"} if ft=="number" else {"type":"integer"}))
                props[fn] = {**psch, "description": fdesc}
                if freq: req_fields.append(fn)
            sch = {"type": "object", "properties": props}
            if req_fields: sch["required"] = req_fields
            reqbody = {"required": True, "content": {
                "application/x-www-form-urlencoded": {"schema": sch}}}
        else:  # json
            if data:
                sch = {"$ref": "#/components/schemas/" + data}
            else:
                sch = {"type": "object", "additionalProperties": True}
            reqbody = {"required": True, "content": {"application/json": {"schema": sch}}}

    # result -> response schema
    r = e["result"]
    if r[0] == "obj":
        rschema = {"$ref": "#/components/schemas/ResponseWrapper"}
    elif r[0] == "int":
        rschema = {"$ref": "#/components/schemas/ResponseWrapper_Integer"}
    elif r[0] == "ref":
        rschema = {"$ref": "#/components/schemas/ResponseWrapper_" + r[1]}
    elif r[0] == "list":
        rschema = {"$ref": "#/components/schemas/ResponseWrapper_ListResponse_" + r[1]}

    resp = {"200": {"description": "成功（code=0 表示成功，见 ResponseWrapper）",
                    "content": {"application/json": {"schema": rschema}}}}
    op = {"tags": [e["tag"]], "summary": e["summary"], "operationId": e["opId"],
          "responses": resp}
    if params: op["parameters"] = params
    if reqbody: op["requestBody"] = reqbody
    paths[p][e["method"]] = op

# auto-generate wrapper schemas
for e in EP:
    r = e["result"]
    if r[0] == "int":
        S.setdefault("ResponseWrapper_Integer",
            wrapper_schema(prop(INT)))
    elif r[0] == "ref":
        S.setdefault("ResponseWrapper_" + r[1],
            wrapper_schema(prop(("ref", r[1]))))
    elif r[0] == "list":
        elem = r[1]
        elem_prop = prop(("ref", elem)) if elem in S or True else prop(OBJ)
        S.setdefault("ResponseWrapper_ListResponse_" + elem, wrapper_schema(
            listresponse_schema(prop(("ref", elem)))))

spec = {
    "openapi": "3.0.3",
    "info": {
        "title": "网易智造 App API",
        "version": "5.3.5",
        "description": "从 网易智造_5.3.5.apk 反编译提取（Retrofit + OkHttp + Gson）。"
                       "基础 URL 线上为 https://3c.163.com，认证基于 Cookie（ONE_TOKEN/ONE_TOKEN_ID/UA-INFO）。"
                       "统一响应结构 ResponseWrapper：code=0 成功，result 为业务数据。",
    },
    "servers": [
        {"url": "https://3c.163.com", "description": "线上/Release"},
        {"url": "https://t2.3c.163.com", "description": "Alpha/Beta"},
        {"url": "https://t.3c.163.com", "description": "Develop"},
    ],
    "tags": [{"name": k, "description": v} for k, v in TAGDESC.items()],
    "paths": paths,
    "components": {"schemas": S},
}

# 输出到仓库根目录（本脚本位于 scripts/ 下，向上两级即仓库根）
out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "openapi.yaml")
with open(out, "w", encoding="utf-8") as f:
    yaml.dump(spec, f, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)
print("written:", out)
print("paths:", len(paths), "schemas:", len(S))
