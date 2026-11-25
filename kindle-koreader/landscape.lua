local Device = require("device")
local Event = require("ui/event")
local JSON = require("json")
local NetworkMgr = require("ui/network/manager")
local UIManager = require("ui/uimanager")
local http = require("socket.http")
local ltn12 = require("ltn12")
local mime = require("mime")
local socketutil = require("socketutil")
local logger = require("logger")

local Landscape = {}
local Screen = Device.screen
local PREFIX = "/api/kindle/landscape"
local WIDTH, HEIGHT = 1024, 758
local INTERVAL = 30
local pages = { todo = true, calendar = true, pomodoro = true }

local function privateBase(url)
    if type(url) ~= "string" then return nil end
    local host, port = url:match("^http://([%d.]+):?(%d*)/?$")
    if not host then return nil end
    local a, b, c, d = host:match("^(%d+)%.(%d+)%.(%d+)%.(%d+)$")
    a, b, c, d = tonumber(a), tonumber(b), tonumber(c), tonumber(d)
    if not (a and a <= 255 and b <= 255 and c <= 255 and d <= 255) then return nil end
    local canonical = string.format("%d.%d.%d.%d", a, b, c, d)
    if host ~= canonical then return nil end
    if a == 10 or (a == 172 and b >= 16 and b <= 31) or (a == 192 and b == 168) then
        if port == "" then return "http://" .. canonical end
        local number = tonumber(port)
        if number >= 1 and number <= 65535 then return "http://" .. canonical .. ":" .. number end
    end
end

local function request(session, method, path, payload)
    local chunks, size = {}, 0
    local options = {
        url = session.base .. PREFIX .. path,
        method = method,
        redirect = false,
        headers = { ["access-token"] = session.token, ["Accept"] = "application/json" },
        sink = function(chunk, err)
            if chunk then
                size = size + #chunk
                if size > 1024 * 1024 then return nil, "Response too large" end
                chunks[#chunks + 1] = chunk
            end
            if err then return nil, err end
            return 1
        end,
    }
    if method == "GET" then
        local ok, battery = pcall(function()
            if Device:hasBattery() then return Device:getPowerDevice():getCapacity() end
        end)
        if ok and type(battery) == "number" and battery >= 0 and battery <= 100 then
            options.headers["percent-charged"] = tostring(math.floor(battery + 0.5))
        end
        -- Omit Wi-Fi if the current action may have turned it on temporarily.
        local wifi_ok, wifi_stays_on = pcall(function()
            return NetworkMgr:isConnected() and (not NetworkMgr:getBeforeActionFlag() or
                G_reader_settings:readSetting("wifi_disable_action") == "leave_on")
        end)
        if wifi_ok and wifi_stays_on then options.headers["dashboard-wifi"] = "connected" end
    end
    if payload then
        local body = JSON.encode(payload)
        options.headers["Content-Type"] = "application/json"
        options.headers["Content-Length"] = tostring(#body)
        options.source = ltn12.source.string(body)
    end
    socketutil:set_timeout(6, 12)
    local ok, result, status = pcall(http.request, options)
    socketutil:reset_timeout()
    if ok and result == 1 then return tonumber(status), table.concat(chunks) end
end

local function validNumber(value, min, max)
    return type(value) == "number" and value >= min and value <= max and value % 1 == 0
end

local function decodeFrame(body, page)
    local ok, frame = pcall(JSON.decode, body)
    if not ok or type(frame) ~= "table" or frame.page ~= page or
        not validNumber(frame.number, 1, 2147483647) or frame.width ~= WIDTH or frame.height ~= HEIGHT or
        frame.refresh_rate ~= INTERVAL or type(frame.filename) ~= "string" or
        not frame.filename:match("^landscape%-%x+%.png$") or type(frame.png) ~= "string" or
        type(frame.regions) ~= "table" or #frame.regions < 3 or #frame.regions > 11 then
        return nil
    end
    for _, region in ipairs(frame.regions) do
        if type(region) ~= "table" or not validNumber(region.x, 0, WIDTH - 1) or
            not validNumber(region.y, 0, HEIGHT - 1) or not validNumber(region.w, 1, WIDTH - region.x) or
            not validNumber(region.h, 1, HEIGHT - region.y) then return nil end
        if region.action == "navigate" then
            if not pages[region.page] or not validNumber(region.number, 1, 2147483647) then return nil end
        elseif region.action == "complete" then
            if page ~= "todo" or not validNumber(region.task_id, 1, 9007199254740991) or
                type(region.completed) ~= "boolean" or type(region.capability) ~= "string" then return nil end
        else
            return nil
        end
    end
    local png = mime.unb64(frame.png)
    -- Reject a mismatched IHDR before mapping any gestures against the frame.
    if not png or png:sub(1, 8) ~= "\137PNG\r\n\26\n" or
        png:sub(13, 24) ~= "IHDR\0\0\4\0\0\0\2\246" then return nil end
    frame.png = png
    return frame
end

function Landscape.hit(frame, bounds, x, y)
    x, y = x - bounds.x, y - bounds.y
    if x < 0 or y < 0 or x >= bounds.w or y >= bounds.h then return nil end
    x, y = math.floor(x * frame.width / bounds.w), math.floor(y * frame.height / bounds.h)
    for _, region in ipairs(frame.regions) do
        if x >= region.x and x < region.x + region.w and y >= region.y and y < region.y + region.h then
            return region
        end
    end
end

local function schedule(session)
    UIManager:unschedule(session.refresh)
    UIManager:scheduleIn(INTERVAL, session.refresh)
end

local function rotate(plugin, target)
    if Screen:getRotationMode() == target then return end
    Screen:setRotationMode(target)
    local size = Screen:getSize()
    if plugin.ui.onScreenResize then plugin.ui:onScreenResize(size) end
    plugin.ui:handleEvent(Event:new("SetDimensions", size))
    plugin.ui:handleEvent(Event:new("InitScrollPageStates"))
    UIManager:setDirty("all", "full")
end

local function stop(plugin)
    local session = plugin.landscape_session
    if not session then return end
    plugin.landscape_session = nil
    UIManager:unschedule(session.refresh)
    if session.widget then
        UIManager:close(session.widget)
        plugin.image_widget = nil
    end
    if session.rotation ~= nil then rotate(plugin, session.rotation) end
end

local function fetch(plugin, session, page, number, change)
    if plugin.landscape_session ~= session or session.suspended or session.pending then return end
    UIManager:unschedule(session.refresh)
    local attempt = {}
    session.pending = attempt
    -- The Wi-Fi manager may never invoke its callback after a failed connection.
    UIManager:scheduleIn(INTERVAL, session.refresh)
    NetworkMgr:runWhenConnected(function()
        if plugin.landscape_session ~= session or session.pending ~= attempt or session.suspended then return end
        local ok, reason = pcall(function()
            if change then
                local status = request(session, "PUT", "/tasks/" .. string.format("%.0f", change.task_id) .. "/completion",
                    { completed = change.completed, capability = change.capability })
                -- After a rejected or uncertain update, wait for the normal refresh.
                -- The last successfully displayed image and regions remain paired.
                if status ~= 204 then return end
            end
            local status, body = request(session, "GET", "/frame?page=" .. page .. "&number=" .. number)
            local frame = status == 200 and decodeFrame(body, page)
            if not frame then return end
            if session.rotation == nil then
                session.rotation = Screen:getRotationMode()
            end
            if Screen:getWidth() < Screen:getHeight() then
                rotate(plugin, Screen.DEVICE_ROTATED_CLOCKWISE)
            end
            local function handleTap(widget, gesture)
                if session.frame ~= frame or session.widget ~= widget or not gesture or not gesture.pos or
                    Screen:getRotationMode() ~= session.display_rotation or
                    Screen:getWidth() ~= widget.dimen.w or Screen:getHeight() ~= widget.dimen.h then return end
                local region = Landscape.hit(frame, widget.dimen, gesture.pos.x, gesture.pos.y)
                if not region then return end
                if region.action == "navigate" then
                    if region.page ~= frame.page or region.number ~= frame.number then
                        fetch(plugin, session, region.page, region.number)
                    end
                else
                    fetch(plugin, session, frame.page, frame.number, region)
                end
            end
            if plugin:displayImage(nil, {
                png = frame.png,
                tap = handleTap,
                close = function() stop(plugin) end,
            }) then
                session.widget = plugin.image_widget
                UIManager:forceRePaint()
                if UIManager.waitForVSync then UIManager:waitForVSync() end
                session.frame = frame
                session.display_rotation = Screen:getRotationMode()
                frame.png = nil
            end
        end)
        if not ok then logger.warn("TRMNL landscape frame failed", type(reason)) end
        if not session.widget and session.rotation ~= nil then
            rotate(plugin, session.rotation)
            session.rotation = nil
        end
        session.pending = nil
        NetworkMgr:afterWifiAction()
        if plugin.landscape_session == session and not session.suspended then schedule(session) end
    end)
end

function Landscape.attach(plugin)
    local addToMainMenu = plugin.addToMainMenu
    local onSuspend, onResume, onCloseWidget = plugin.onSuspend, plugin.onResume, plugin.onCloseWidget
    local fetchAndDisplay, startAutoRefresh = plugin.fetchAndDisplay, plugin.startAutoRefresh

    function plugin:startLandscape()
        if self.landscape_session or self.auto_refresh_enabled or self.image_widget then return end
        local base = privateBase(self.settings.base_url)
        local token = self.settings.api_key
        if not Device:isTouchDevice() or not base or not token or token == "" then
            self:showError("Interactive dashboard requires a touchscreen, a private IPv4 HTTP Base URL and an API key.")
            return
        end
        local session = { base = base, token = token }
        session.refresh = function()
            session.pending = nil
            local frame = session.frame
            fetch(self, session, frame and frame.page or "todo", frame and frame.number or 1)
        end
        self.portrait_generation = (self.portrait_generation or 0) + 1
        self.landscape_session = session
        fetch(self, session, "todo", 1)
    end

    function plugin:addToMainMenu(menu_items)
        addToMainMenu(self, menu_items)
        table.insert(menu_items.trmnl.sub_item_table, 1, {
            text = "Start interactive landscape dashboard",
            callback = function() self:startLandscape() end,
        })
        table.insert(menu_items.trmnl.sub_item_table, 2, {
            text = "Stop interactive landscape dashboard",
            show_func = function() return self.landscape_session ~= nil end,
            callback = function() stop(self) end,
        })
    end

    function plugin:fetchAndDisplay()
        local session = self.landscape_session
        if not session then return fetchAndDisplay(self) end
        local frame = session.frame
        fetch(self, session, frame and frame.page or "todo", frame and frame.number or 1)
    end

    function plugin:startAutoRefresh()
        if not self.landscape_session then return startAutoRefresh(self) end
    end

    function plugin:onSuspend()
        local session = self.landscape_session
        if session then
            session.suspended = true
            session.pending = nil
            UIManager:unschedule(session.refresh)
        end
        onSuspend(self)
    end

    function plugin:onResume()
        local session = self.landscape_session
        if not session then return onResume(self) end
        session.suspended = false
        schedule(session)
    end

    function plugin:onCloseWidget()
        stop(self)
        onCloseWidget(self)
    end
end

return Landscape
