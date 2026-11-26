local Blitbuffer = require("ffi/blitbuffer")
local CenterContainer = require("ui/widget/container/centercontainer")
local Device = require("device")
local FrameContainer = require("ui/widget/container/framecontainer")
local Geom = require("ui/geometry")
local ImageWidget = require("ui/widget/imagewidget")
local UIManager = require("ui/uimanager")
local logger = require("logger")

local Sleep = {}
local Screen = Device.screen

function Sleep.closeScreen(state)
    if not state.widget then return end
    local widget = state.widget
    state.widget = nil
    if not pcall(UIManager.close, UIManager, widget, "full") then
        logger.warn("TRMNL landscape: sleep screen close failed")
    end
end

function Sleep.showScreen(state)
    local w, h = Screen:getWidth(), Screen:getHeight()
    if state.widget and state.width == w and state.height == h
        and UIManager:getTopmostVisibleWidget() == state.widget then return end
    Sleep.closeScreen(state)

    local ok = pcall(function()
        state.widget = FrameContainer:new{
            modal = true,
            covers_fullscreen = true,
            background = Blitbuffer.COLOR_WHITE,
            bordersize = 0,
            padding = 0,
            margin = 0,
            CenterContainer:new{
                dimen = Geom:new{ w = w, h = h },
                ImageWidget:new{
                    file = state.image,
                    file_do_cache = false,
                    width = w,
                    height = h,
                    scale_factor = 0,
                },
            },
        }
        state.width, state.height = w, h
        UIManager:show(state.widget, "full")
        UIManager:forceRePaint()
        if UIManager.waitForVSync then UIManager:waitForVSync() end
    end)
    if not ok then
        Sleep.closeScreen(state)
        logger.warn("TRMNL landscape: sleep screen unavailable")
    end
end

function Sleep.prepare(image)
    local state = { image = image }
    Sleep.showScreen(state)
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
    return state
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

return Sleep
