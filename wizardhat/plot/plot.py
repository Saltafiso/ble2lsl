"""Plotting of data in `data.Data` objects.

Rough implementation of a standalone bokeh server.

Currently just grabs the most recent sample from Data.data every time the
periodic callback executes. This is probably not the best way to do it, because
the sampling rate is arbitrarily based on the value for
`add_periodic_callback()`. For example, you can set the callback time to
something faster than the sampling rate and you'll see that each value in
`streamer.data.data` gets sampled a few times (starts to look like a step
function). Right now there's no good way to check that we're not dropping
samples when updating.

Also just two manually retrieved channels for now as a proof of concept, but
the gridplot method seems to work well for this.

TODO:
    * Figure out sampling method- possibly using Data's self.updated attribute
        to trigger an update? Maybe we can update everything "in-place" because
        data.data already has a built-in window..
    * Automatically determine device name/set to title?
"""

from functools import partial
from threading import Thread

from bokeh.layouts import gridplot
from bokeh.models import ColumnDataSource
from bokeh.palettes import all_palettes as palettes
from bokeh.plotting import figure
from bokeh.server.server import Server
from tornado import gen


class Plotter():
    """Base class for plotting."""

    def __init__(self, data):
        """Construct a `Plotter` instance.

        Args:
            data (data.Data): Data object managing data to be plotted.
            plot_params (dict): Plot display parameters.
        """
        self.data = data
        # output_file('WizardHat Plotter.html')


class Lines():
    """Multiple (stacked) line plots.

    Expects a two-dimensional `data.Data` object (such as `TimeSeries`) where
    all columns after the first give the data used to plot individual lines.
    Multiple data sources may be given in a list, assuming they have the same
    form (number of channels and rows/samples); the user can cycle between
    plots of each data source with the 'D' key.
    """

    def __init__(self, data, n_samples=5000, palette='Category10',
                 bgcolor="white", autostart=True):
        """Construct a `Lines` instance.
        Args:
            data (data.Data or List[data.Data]): Data object(s) managing data
                to be plotted. Multiple objects may be passed in a list, in
                which case the plot can cycle through plotting the data in
                each object by pressing 'd'. However, all data objects passed
                should have a similar form (e.g. `TimeSeries` with same number
                of rows/samples and channels).
            plot_params (dict): Plot display parameters.
        """

        self.data = data

        # TODO: initialize with existing samples in self.data.data
        data_dict = {name: self.data.data[name][:n_samples]
                     #for name in self.data.dtype.names}
        self._source = ColumnDataSource(data_dict)
        self.server = Server({'/': self._app_manager})
        self._update_thread = Thread(target=self._get_new_samples)
        self._n_samples = n_samples

        self._colors = palettes[palette][len(self.data.ch_names)]
        self._bgcolor = bgcolor

        if autostart:
            self.run_server()

    def run_server(self):
        self.server.start()
        self.server.io_loop.add_callback(self.server.show, '/')
        self._update_thread.start()
        self.server.io_loop.start()

    def _app_manager(self, curdoc):
        self._curdoc = curdoc
        self._set_layout()
        self._set_callbacks()

    def _set_layout(self):
        self.plots = []
        for i, ch in enumerate(self.data.ch_names):
            p = figure(plot_height=100,
                       tools="xpan,xwheel_zoom,xbox_zoom,reset",
                       x_axis_type='datetime', y_axis_location="right",y_range=(-10,10))
            p.x_range.follow = "end"  # always follows new data in source
            p.x_range.follow_interval = 5  # in s
            p.x_range.range_padding = 0  # we can play with this stuff
            p.yaxis.axis_label = ch
            p.background_fill_color = self._bgcolor
            # p.background_fill_alpha = 0.5
            p.line(x='time', y=ch, alpha=0.8, line_width=2,
                   color=self._colors[i], source=self._source)
            self.plots.append([p])

    def _set_callbacks(self):
        self._curdoc.add_root(gridplot(self.plots, toolbar_location="left",
                                       plot_width=1000))
        self._curdoc.title = "Dummy EEG Stream"

    @gen.coroutine
    def _update(self, data_dict):
        self._source.stream(data_dict, self._n_samples)

    def _get_new_samples(self):
        while True:
            self.data.updated.wait()
            data_dict = {name: self.data.last_samples[name]
                         for name in self.data.dtype.names}
            try:  # don't freak out if IOLoop
                self._curdoc.add_next_tick_callback(partial(self._update,
                                                            data_dict))
            except AttributeError:
                pass
            self.data.updated.clear()
