import pyqtgraph as pg
from PySide import QtCore, QtGui
from scipy import interpolate


class ShapeControlWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        super(ShapeControlWidget, self).__init__(None)
        self.parent = parent
        self.setupGUI()
        self.cancelButton.pressed.connect(self.cancel)
        self.okButton.pressed.connect(self.interpolateShapes)

    def setupGUI(self):
        self.layout = QtGui.QHBoxLayout()
        self.setLayout(self.layout)
        self.okButton = QtGui.QPushButton("OK")
        self.cancelButton = QtGui.QPushButton("Cancel")
        self.layout.addWidget(self.okButton)
        self.layout.addWidget(self.cancelButton)
        self.setMaximumHeight(50)

        if self.parent is not None:
            self.setParent(self.parent)

    def setParent(self, parent):
        self.parent = parent
        self.parent.layout.insertWidget(0, self)

    def cancel(self):
        self.hide()
        if self.parent is not None:
            # remove ROIs
            active_waves = self.parent.getActivePlots()
            for wave in active_waves:
                plot = self.parent.plots[wave]
                roi = self.parent.plotWidget.rois[wave]
                plot.removeItem(roi)

    def interpolateShapes(self):
        '''
        interpolate y = y(x) from ROIs
        Get parent y array.
        then calculate y = y(x) for each wave
        '''
        if self.parent is None:
            self.cancel()
            return 0
        else:
            arrival_times = {}
            rois = self.parent.plotWidget.rois
            waves = self.parent.getActivePlots()
            for wave in waves:
                # get y = y(x) from ROIs
                points_x, points_y = rois[wave].getPoints()
                print(points_x, points_y)
                f = interpolate.interp1d(points_y, points_x,
                                         bounds_error=False)
                # get parent y array
                y = self.parent.getFullYArray(wave)
                # interpolate to get x == arrival times
                arrival_times[wave] = f(y)
            self.cancel()
            self.parent.setArrivalTimes(arrival_times)
            self.parent.plot_arrival_times_flag = True
            self.parent.controller.showArrivalsAction.trigger()
