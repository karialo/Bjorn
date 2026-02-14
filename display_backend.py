import importlib
import logging
import os
import sys
from types import SimpleNamespace

from PIL import Image


logger = logging.getLogger(__name__)


class WaveshareEPDBackend:
    def __init__(self, epd_type):
        self.epd_type = epd_type
        self.epd = self._load_epd_module()

    def _load_epd_module(self):
        try:
            epd_module_name = f"resources.waveshare_epd.{self.epd_type}"
            epd_module = importlib.import_module(epd_module_name)
            return epd_module.EPD()
        except ImportError as exc:
            logger.error(f"EPD module {self.epd_type} not found: {exc}")
            raise
        except Exception as exc:
            logger.error(f"Error loading EPD module {self.epd_type}: {exc}")
            raise

    def init_full_update(self):
        if hasattr(self.epd, "FULL_UPDATE"):
            self.epd.init(self.epd.FULL_UPDATE)
        elif hasattr(self.epd, "lut_full_update"):
            self.epd.init(self.epd.lut_full_update)
        else:
            self.epd.init()

    def init_partial_update(self):
        if hasattr(self.epd, "PART_UPDATE"):
            self.epd.init(self.epd.PART_UPDATE)
        elif hasattr(self.epd, "lut_partial_update"):
            self.epd.init(self.epd.lut_partial_update)
        else:
            self.epd.init()

    def display_partial(self, image):
        if hasattr(self.epd, "displayPartial"):
            self.epd.displayPartial(self.epd.getbuffer(image))
        else:
            self.epd.display(self.epd.getbuffer(image))

    def clear(self):
        self.epd.Clear()


class DisplayHATMiniBackend:
    WIDTH = 320
    HEIGHT = 240
    FRIENDLY_IMPORT_ERROR = (
        "Display HAT Mini backend requires running on Raspberry Pi with "
        "RPi.GPIO + spidev + ST7789 available (enable SPI)."
    )

    def __init__(self):
        self.epd = SimpleNamespace(width=self.WIDTH, height=self.HEIGHT)
        self.displayhatmini = self._import_displayhatmini()
        self.buffer = Image.new("RGB", (self.WIDTH, self.HEIGHT), (0, 0, 0))
        self.display_device = self._build_display_device()

    def _import_displayhatmini(self):
        vendored_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "third_party",
            "pimoroni_displayhatmini",
        )
        try:
            if vendored_path not in sys.path:
                sys.path.insert(0, vendored_path)
            import displayhatmini

            return displayhatmini
        except ImportError as exc:
            if self._is_pi_dependency_import_error(exc):
                raise ImportError(self.FRIENDLY_IMPORT_ERROR) from exc
            raise ImportError(
                "Unable to import 'displayhatmini' from vendored path "
                f"'{vendored_path}'. Ensure "
                "'third_party/pimoroni_displayhatmini/displayhatmini' exists."
            ) from exc

    @staticmethod
    def _is_pi_dependency_import_error(exc):
        dependency_markers = ("RPi", "RPi.GPIO", "spidev", "ST7789")
        stack = [exc]
        visited = set()

        while stack:
            current = stack.pop()
            if current is None:
                continue

            current_id = id(current)
            if current_id in visited:
                continue
            visited.add(current_id)

            missing_name = getattr(current, "name", None)
            if isinstance(missing_name, str) and missing_name in dependency_markers:
                return True

            current_text = str(current)
            if any(marker in current_text for marker in dependency_markers):
                return True

            stack.append(getattr(current, "__cause__", None))
            stack.append(getattr(current, "__context__", None))

        return False

    def _build_display_device(self):
        display_cls = getattr(self.displayhatmini, "DisplayHATMini", None)
        if display_cls is None:
            return None
        try:
            return display_cls(self.buffer)
        except TypeError:
            return display_cls()

    def _fit_to_canvas(self, image):
        source = image.convert("RGB")
        source.thumbnail((self.WIDTH, self.HEIGHT), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (self.WIDTH, self.HEIGHT), (0, 0, 0))
        paste_x = (self.WIDTH - source.width) // 2
        paste_y = (self.HEIGHT - source.height) // 2
        canvas.paste(source, (paste_x, paste_y))
        return canvas

    def _push_with_instance(self, image):
        if hasattr(self.display_device, "buffer"):
            self.display_device.buffer.paste(image)
        if hasattr(self.display_device, "display"):
            self.display_device.display()
            return
        if hasattr(self.display_device, "show"):
            self.display_device.show()
            return
        if hasattr(self.display_device, "update"):
            self.display_device.update()
            return
        raise RuntimeError("DisplayHATMini backend instance has no render method.")

    def _push_with_module(self, image):
        if hasattr(self.displayhatmini, "display"):
            try:
                self.displayhatmini.display(image)
            except TypeError:
                self.displayhatmini.display()
            return
        if hasattr(self.displayhatmini, "show"):
            try:
                self.displayhatmini.show(image)
            except TypeError:
                self.displayhatmini.show()
            return
        if hasattr(self.displayhatmini, "update"):
            try:
                self.displayhatmini.update(image)
            except TypeError:
                self.displayhatmini.update()
            return
        raise RuntimeError("displayhatmini module has no compatible render API.")

    def init_full_update(self):
        logger.info("Display HAT Mini selected; full update init is a no-op.")

    def init_partial_update(self):
        logger.info("Display HAT Mini selected; partial update init is a no-op.")

    def display_partial(self, image):
        rendered = self._fit_to_canvas(image)
        if self.display_device is not None:
            self._push_with_instance(rendered)
        else:
            self._push_with_module(rendered)

    def clear(self):
        self.display_partial(Image.new("RGB", (self.WIDTH, self.HEIGHT), (0, 0, 0)))


def create_display_backend(config):
    display_driver = config.get("display_driver", "waveshare_epd")
    logger.info(f"Selected display backend: {display_driver}")

    if display_driver == "waveshare_epd":
        epd_type = config.get("epd_type", "epd2in13_V4")
        return WaveshareEPDBackend(epd_type)
    if display_driver == "displayhatmini":
        return DisplayHATMiniBackend()
    raise ValueError(f"Unsupported display_driver '{display_driver}'")
