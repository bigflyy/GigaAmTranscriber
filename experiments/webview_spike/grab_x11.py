"""Save the whole X screen (Xvfb) as PNG using GTK's Gdk."""
import sys
import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk
root = Gdk.get_default_root_window()
pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height())
pixbuf.savev(sys.argv[1], "png", [], [])
