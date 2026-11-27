local Blitbuffer = require("ffi/blitbuffer")
local CenterContainer = require("ui/widget/container/centercontainer")
local Device = require("device")
local Geom = require("ui/geometry")
local ImageWidget = require("ui/widget/imagewidget")
local ScreenSaverWidget = require("ui/widget/screensaverwidget")
local Screensaver = require("ui/screensaver")
local UIManager = require("ui/uimanager")
local logger = require("logger")

local Sleep = {}
local Screen = Device.screen

local function dimLight(state)
    local ok = pcall(function()
        if not Device:hasFrontlight() then return end
        local power = Device:getPowerDevice()
        state.was_on = power:isFrontlightOn()
        if state.was_on then state.brightness = power:frontlightIntensity() end
        state.power = power
        if state.was_on then power:turnOffFrontlight() end
        if power:isFrontlightOn() then error("frontlight remains on") end
        logger.info("TRMNL landscape: frontlight off for sleep")
    end)
    if not ok then logger.warn("TRMNL landscape: frontlight off could not be confirmed") end
end

function Sleep.restoreLight(state)
    if not state.power then return end
    local ok = pcall(function()
        local power = state.power
        if state.was_on then
            if not power:isFrontlightOn() then power:turnOnFrontlight() end
            if power:frontlightIntensity() ~= state.brightness then power:setIntensity(state.brightness) end
        elseif power:isFrontlightOn() then
            power:turnOffFrontlight()
        end
        if power:isFrontlightOn() ~= state.was_on or
            (state.was_on and power:frontlightIntensity() ~= state.brightness) then
            error("frontlight state not restored")
        end
        logger.info("TRMNL landscape: frontlight state restored")
    end)
    if not ok then logger.warn("TRMNL landscape: frontlight restoration could not be confirmed") end
end

function Sleep.closeScreen(state)
    if Screensaver.screensaver_widget ~= state.widget then return true end
    local ok = type(Screensaver.close_widget) == "function" and pcall(Screensaver.close_widget, Screensaver)
    if not ok then ok = pcall(UIManager.close, UIManager, state.widget, "full") end
    if not ok then logger.warn("TRMNL landscape: native sleep screen close failed") end
    return ok
end

function Sleep.showScreen(session)
    if session.sleep then return true end
    if Screensaver.screensaver_widget or Screensaver.screensaver_lock_widget then return false end
    local state = {}
    local ok = pcall(function()
        if Screen:getRotationMode() ~= session.display_rotation then
            Screen:setRotationMode(session.display_rotation)
        end
        local w, h = Screen:getWidth(), Screen:getHeight()
        state.widget = ScreenSaverWidget:new{
            modal = true,
            covers_fullscreen = true,
            background = Blitbuffer.COLOR_WHITE,
            widget = CenterContainer:new{
                dimen = Geom:new{ w = w, h = h },
                ImageWidget:new{
                    file = session.sleep_image,
                    file_do_cache = false,
                    width = w,
                    height = h,
                    scale_factor = 0,
                },
            },
        }
        session.sleep = state
        Device.orig_rotation_mode = nil
        Device.screen_saver_mode = true
        Screensaver.screensaver_widget = state.widget
        UIManager:show(state.widget, "full")
        UIManager:forceRePaint()
        if UIManager.waitForVSync then UIManager:waitForVSync() end
        dimLight(state)
        logger.info("TRMNL landscape: native moon screensaver shown", Screen:getRotationMode())
    end)
    if not ok then
        if state.widget then Sleep.closeScreen(state) end
        Sleep.restoreLight(state)
        session.sleep = nil
        logger.warn("TRMNL landscape: native moon screensaver unavailable")
    end
    return ok
end

function Sleep.install(session, active)
    local setup, show, close = Screensaver.setup, Screensaver.show, Screensaver.close
    local custom
    local dashboardSetup = function(saver, event, ...)
        custom = not event and active()
        if custom then return end
        return setup(saver, event, ...)
    end
    local dashboardShow = function(saver, ...)
        if custom then
            custom = nil
            if active() and Sleep.showScreen(session) then return end
            setup(saver)
        end
        return show(saver, ...)
    end
    local dashboardClose = function(saver, ...)
        -- The physical button is sufficient to leave this dashboard screensaver.
        if session.sleep and saver.screensaver_widget == session.sleep.widget
            and Sleep.closeScreen(session.sleep) then return true end
        return close(saver, ...)
    end
    Screensaver.setup, Screensaver.show, Screensaver.close = dashboardSetup, dashboardShow, dashboardClose
    return function()
        if Screensaver.setup == dashboardSetup then Screensaver.setup = setup end
        if Screensaver.show == dashboardShow then Screensaver.show = show end
        if Screensaver.close == dashboardClose then Screensaver.close = close end
    end
end

return Sleep
