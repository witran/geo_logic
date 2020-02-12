import gi as gtk_import
gtk_import.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import numpy as np
from geo_object import *
from parse import Parser, type_to_c
import primitive_pred
from collections import defaultdict
from tool_step import ToolStep, proof_checker
from file_chooser import select_file_open, select_file_save
from stop_watch import print_times, StopWatch
from itertools import islice
from viewport import Viewport
from graphical_env import GraphicalEnv
from movable_tools import MovableTool
from basic_tools import load_tools, ImportedTools
from gtool_general import GToolDict
from gtool import ObjSelector, GTool, GToolMove, GToolHide
from gtool_constr import ComboPoint, ComboLine, ComboPerpLine, ComboCircle, ComboCircumCircle

class Drawing(Gtk.Window):

    def make_toolbox(self, max_height = 45):
        self.tool_buttons = dict()
        self.imported_tools = load_tools("macros.gl")

        self.general_tools = GToolDict(self.imported_tools.tool_dict)
        tool_names = sorted(self.general_tools.name_to_prefixes.keys())

        def change_tool(button, name):
            if button.get_active():
                self.viewport.set_tool(self.general_tools.make_tool(name))

        num_names = len(tool_names)
        num_columns = (num_names-1) // max_height + 1
        max_height = (num_names-1) // num_columns + 1

        hbox = Gtk.HBox()
        counter = max_height
        button1 = None
        vbox = None
        for name in tool_names:
            if counter == max_height:
                vbox = Gtk.VBox()
                hbox.add(vbox)
                counter = 0
            counter += 1
            if button1 is None:
                button1 = Gtk.RadioButton.new_with_label_from_widget(button1, name)
                button = button1
            else:
                button = Gtk.RadioButton.new_from_widget(button1)
                button.set_label(name)
            button.connect("toggled", change_tool, name)
            self.tool_buttons[name] = button
            vbox.add(button)
        return hbox

    def __init__(self):
        super(Drawing, self).__init__()
        self.mb_grasp = None
        self.key_to_tool = {
            #'l': "p_line",
            #'c': "p_circum",
            '9': "circle9",
            'i': "incircle",
            'e': "excircle",
            #'x': "p_intersect",
            #'X': "p_intersect_rem",
            'question': "lies_on",
            #'exclam': "fake_lies_on",
            '1': "point_on_circle",
            '2': "point_to_circle",
            '3': "cong_sss",
        }
        self.key_to_gtool = {
            'x' : (ComboPoint, "point"),
            'l' : (ComboLine, "line"),
            't' : (ComboPerpLine, "perpline"),
            'c' : (ComboCircle, "circle"),
            'o' : (ComboCircumCircle, "circumcircle"),
            'm' : (GToolMove, "grab"),
            'h' : (GToolHide, "hide"),
        }
        self.default_fname = None

        self.set_events(Gdk.EventMask.KEY_PRESS_MASK |
                        Gdk.EventMask.KEY_RELEASE_MASK)


        hbox = Gtk.HPaned()
        hbox.add(self.make_toolbox())

        self.env = GraphicalEnv(self.imported_tools)
        self.viewport = Viewport(self.env)
        self.viewport.set_tool(ComboPoint(), "point")

        self.darea_vbox = Gtk.VBox()
        self.darea_vbox.add(self.viewport.darea)
        self.progress_bar = Gtk.ProgressBar(show_text=False)
        self.darea_vbox.pack_end(self.progress_bar, False, False, 0)
        hbox.add(self.darea_vbox)
        self.add(hbox)

        self.connect("key-press-event", self.on_key_press)
        self.connect("key-release-event", self.on_key_release)

        self.set_title("Drawing")
        self.resize(1200, 400)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", Gtk.main_quit)
        self.show_all()

        def update_progress_bar(done, size):
            if size == 0: self.progress_bar.set_fraction(0)
            else: self.progress_bar.set_fraction(done / size)
            return False
        def update_progress_bar_idle(done, size):
            GLib.idle_add(update_progress_bar, done, size)

        proof_checker.paralelize(progress_hook = update_progress_bar_idle)

    def load_file(self, fname):
        if fname is None: return
        self.default_fname = fname
        parser = Parser(self.imported_tools.tool_dict)
        parser.parse_file(fname, axioms = False)
        loaded_tool = parser.tool_dict['_', ()]
        visible = set(loaded_tool.result)
        if not visible: visible = None
        self.env.set_steps(loaded_tool.assumptions, visible = visible)
    def restart(self):
        self.default_fname = None
        self.env.set_steps(())

    def save_file(self, fname):
        if fname is None: return
        print("saving to '{}'".format(fname))
        self.default_fname = fname
        with open(fname, 'w') as f:
            visible = [
                "x{}:{}".format(gi, type_to_c[self.env.gi_to_type(gi)])
                for gi,hidden in enumerate(self.env.gi_to_hidden)
                if not hidden
            ]
            f.write('_ -> {}\n'.format(' '.join(sorted(visible))))
            i = 0
            for step in self.env.steps:
                i2 = i+len(step.tool.out_types)
                tokens = ['x{}'.format(x) for x in range(i,i2)]
                tokens.append('<-')
                tokens.append(step.tool.name)
                tokens.extend(map(str, step.meta_args))
                tokens.extend('x{}'.format(x) for x in step.local_args)
                f.write('  '+' '.join(tokens)+'\n')
                i = i2


    def on_key_press(self,w,e):

        keyval = e.keyval
        keyval_name = Gdk.keyval_name(keyval)
        ctrl = (e.state & Gdk.ModifierType.CONTROL_MASK)
        if keyval_name == 'BackSpace':
            self.env.pop_step()
        elif keyval_name == 'equal':
            self.env.redo()
        elif keyval_name == "Escape":
            print_times()
            Gtk.main_quit()
        elif ctrl and keyval_name == 'o':
            fname = select_file_open(self)
            self.load_file(fname)
        elif ctrl and keyval_name == 'S':
            fname = select_file_save(self)
            self.save_file(fname)
        elif ctrl and keyval_name == 's':
            fname = self.default_fname
            if fname is None: fname = select_file_save(self)
            self.save_file(fname)
        elif ctrl and keyval_name == 'n':
            self.restart()
        elif not ctrl and keyval_name in self.key_to_gtool:
            gtool, name = self.key_to_gtool[keyval_name]
            print("change tool -> {}".format(gtool.__name__))
            self.viewport.set_tool(gtool(), name)
        elif not ctrl and keyval_name in self.key_to_tool:
            tool_name = self.key_to_tool[keyval_name]
            self.tool_buttons[tool_name].set_active(True)
        elif keyval_name.startswith("Shift"):
            self.viewport.update_shift_pressed(True)
            self.viewport.darea.queue_draw()
            return False
        else:
            #print(keyval_name)
            return False

        if self.env.view_changed:
            self.viewport.update_shift_pressed(e)
            self.viewport.gtool.reset()
            self.viewport.darea.queue_draw()
        return True

    def on_key_release(self,w,e):
        keyval_name = Gdk.keyval_name(e.keyval)
        if keyval_name.startswith("Shift"):
            self.viewport.update_shift_pressed(False)
            self.viewport.darea.queue_draw()

if __name__ == "__main__":
    win = Drawing()
    Gtk.main()
