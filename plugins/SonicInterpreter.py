# coding: UTF-8
import sys,os
import pyqtgraph as pg
from PySide import QtGui, QtCore
from pyqtgraph.parametertree import Parameter, ParameterTree
from pyqtgraph.parametertree import types as pTypes
from pyqtgraph.Point import Point
import numpy as np
import pickle

# custom modules
from TCI.widgets.SonicViewer import SonicViewer
from TCI.lib.readtrc import read_TRC
from TCI.lib.functions import *
from TCI.widgets.ShapeControlWidget import ShapeControlWidget
from TCI.lib.logger import logger
from TCI.widgets.InterpretationSettingsWidget import InterpretationSettingsWidget
from TCI.widgets.BindingWidget import BindingWidget
from TCI.lib.write_csv import write_csv

BadBindingMessage = '''
Duplicates found in the comments column.
This is bad. I will do my best to
square things away, but don't rely on me.
'''

FILE_DIALOG_TITLE = 'Open files'
WAVE_TYPES = ['P','Sx','Sy']
TRACK_NUMBER_LABEL = "Track #"
VIEW_MODES = ['Contours', 'WaveForms']

class SonicInterpreter:
    '''
    Class responsible for interaction of SonicViewerWidget
    and dataviewer class
    '''
    def __init__(self, parent=None):
        self.parent = parent
        self.progressDialog = QtGui.QProgressDialog()
        self.sonicViewer = SonicViewer(parent=parent, controller=self)
        self.interpretationSettings = InterpretationSettingsWidget()
        self.moduliWidget = BindingWidget(parents=[parent, self])
        self.current_data_set = None
        self.all_tables = {}
        self.all_geo_indices = {}
        self.all_indices = {}
        self.all_times = {}

        if parent is not None:
            self.setupActions()
            self.parent.sigSettingGUI.connect(self.modifyParentMenu)
            self.parent.sigNewDataSet.connect(lambda: self.setEnabled(False))
            self.parent.sigLoadDataSet.connect(self.setDataSet)
            self.interpretationSettings.okButton.pressed.connect(self.runModuliWidget)

    def setDataSet(self, data_set):
        '''
        Save previous data to the older data set name
        Then load data from the existing global data dictionary
        '''
        # First save data with the old data set key
        if self.current_data_set is not None:
            logger.info('Saving data set %s'%(self.current_data_set))
            self.all_tables[self.current_data_set] = self.sonicViewer.table
            self.all_geo_indices[self.current_data_set] = self.geo_indices
            self.all_indices[self.current_data_set] = self.indices
            self.sonicViewer.plot_arrival_times_flag = False
            self.all_times[self.current_data_set] = self.times

        # get sonic table for the current data set
        if data_set in self.all_tables.keys():
            logger.info("found data: %s"%(data_set))
            self.current_data_set = data_set
            self.sonicViewer.setSonicTable(self.all_tables[data_set])
            self.geo_indices = self.all_geo_indices[data_set]
            self.indices = self.all_indices[data_set]
            self.times = self.all_times[data_set]
            self.sonicViewer.setIndices(self.indices, self.geo_indices)
            # self.sonicViewer.plot_arrival_times_flag = False
            length = self.parent.props['length']
            self.interpretationSettings.lengthLine.setValue(length)
            # moduli action disabled cause arrival times not stored
            self.moduliAction.setEnabled(False)
            self.sonicViewer.arrivalsPicked = False
            self.setEnabled()
            self.sonicViewer.plot()
        else:
            self.setEnabled(False)

    def loadFileDialog(self):
        '''
        shows file dialog and calls loadData upon selecting
        files
        '''
        lastdir = self.parent.checkForLastDir()
        filter_mask = "Sonic data files (*.TRC *.txt)"
        filenames = QtGui.QFileDialog.getOpenFileNames(None,
            FILE_DIALOG_TITLE, "%s"%(lastdir), filter_mask)[0]

        if filenames != []:
            self.loadData(filenames)
            self.addSonicTab()
            self.bindData()
            self.sonicViewer.setEnabled()
            self.sonicViewer.plot()
            self.createYActions()
            self.setYParameters()

    def addSonicTab(self):
        '''
        Adds sonic tab to parent. If it exists just activates it
        '''
        tab_bar = self.parent.tabWidget
        if tab_bar.indexOf(self.sonicViewer) == -1:
            tab_bar.addTab(self.sonicViewer, "Sonic")
        tab_bar.setCurrentWidget(self.sonicViewer)

    def loadData(self, filenames):
        '''
        Read the supplied files.
        show progress dialog during that operations
        '''
        n_files = len(filenames)
        raw_data = {"P":{}, "Sx":{}, "Sy":{}}
        self.progressDialog.show()

        # iterate through files
        i = 0
        for f in filenames:
            fdir, fname = os.path.split(f)
            # check file extension
            if '.TRC' in fname:
                waves = read_TRC(f)
                # determine what wave this thing pertains to
                wave_type_inferred = False
                for wave_name in WAVE_TYPES:
                    if wave_name  in fname:
                        raw_data[wave_name][fname] = waves
                        wave_type_inferred = True
                if not wave_type_inferred:
                    logger.error("Could not infer wave type for %s"%(fname))
            else:
                logger.error('unknown extension in %s'%(fname))
            i += 1
            self.progressDialog.setValue(float(i)/n_files*100)
        self.progressDialog.hide()

        # organize data
        self.sonicViewer.setRawData(raw_data)
        self.setEnabled()
        # self.parent.tabWidget.setCurrentWidget(self.sonicViewer)


    def setupActions(self):
        # add entry to load sonic files
        self.loadSonicDataAction = QtGui.QAction('Load sonic', self.parent)
        self.parent.loadSonicDataAction = self.loadSonicDataAction
        self.loadSonicDataAction.triggered.connect(self.loadFileDialog)

        self.autoScaleAction = QtGui.QAction('Auto scale', self.parent,
                                             checkable=True,
                                             shortcut='Ctrl+S')
        self.autoScaleAction.setChecked(True)
        self.showArrivalsAction = QtGui.QAction('Arrivals', self.parent,
                                                checkable=True)
        # view menu
        self.showArrivalsAction.setDisabled(True)
        # self.showTableAction = QtGui.QAction('Table', self.parent)
        # self.editGradientsAction = QtGui.QAction('Edit Gradients', self.parent)
        self.invertYAction = QtGui.QAction('Invert y axis', self.parent,
                                           checkable=True)
        # mode menu
        self.modeGroup = QtGui.QActionGroup(self.parent)
        self.waveFormAction = QtGui.QAction('Wave Forms', self.parent,
                                            checkable=True)
        self.contourAction = QtGui.QAction('Contours', self.parent,
                                           checkable=True)
        self.waveFormAction.setActionGroup(self.modeGroup)
        self.contourAction.setActionGroup(self.modeGroup)
        if self.sonicViewer.mode == 'Contours':
            self.contourAction.setChecked(True)
        else:
            self.waveFormAction.setChecked(True)

        # interpretation menu
        # self.pickArrivalsAction = QtGui.QAction('Pick arrivals', self.parent)
        # self.handPickArrivalsAction = QtGui.QAction('Hand pick', self.parent,
        #                                             checkable=True)
        # self.handPickArrivalsAction.setDisabled(True)
        # self.pickArrivalsAction.setDisabled(True)

        self.shapeArrivalsAction = QtGui.QAction('Shape pick', self.parent)
        self.moduliAction = QtGui.QAction('Elastic moduli', self.parent)
        self.moduliAction.setDisabled(True)
        # self.handPickArrivalsAction.setDisabled(True)

        self.showFFTMagnitudeAction = QtGui.QAction('Fourrier magnitude',
                                                        self.parent)
        self.showFFTPhaseAction = QtGui.QAction('Fourrier phases',
                                                     self.parent)
        self.filteringAction = QtGui.QAction('Frequency filtering',
                                             self.parent,
                                             checkable=True)
        # active wave types
        self.pWaveAction = QtGui.QAction('P wave', self.parent, checkable=True)
        self.sxWaveAction = QtGui.QAction('Sx wave', self.parent, checkable=True)
        self.syWaveAction = QtGui.QAction('Sy wave', self.parent, checkable=True)
        self.pWaveAction.setChecked(True)
        self.sxWaveAction.setChecked(True)
        self.syWaveAction.setChecked(True)

        # export arrival times in file menu
        self.exportArrivalsAction = QtGui.QAction(
            'Export Arrival Times', self.parent)
        self.exportModuliAction = QtGui.QAction(
            'Export Moduli', self.parent)

        # dict to store actions for y Axis
        self.yAxisActions = {}
        self.yAxisGroup = QtGui.QActionGroup(self.parent)
        self.yAxisActions[TRACK_NUMBER_LABEL] = QtGui.QAction(
            TRACK_NUMBER_LABEL, self.parent, checkable=True)
        self.yAxisActions[TRACK_NUMBER_LABEL].setActionGroup(self.yAxisGroup)
        self.yAxisActions[TRACK_NUMBER_LABEL].setChecked(True)

    def yLabel(self):
        for label in self.yAxisActions.keys():
            if self.yAxisActions[label].isChecked():
                return label

    def modifyParentMenu(self):
        # setting up the menu bar
        menuBar = self.parent.menuBar

        # FILE MENU
        self.parent.fileMenu.insertAction(self.parent.saveButton,
                                          self.loadSonicDataAction)
        self.parent.fileMenu.insertAction(self.parent.exitAction,
                                          self.exportArrivalsAction)
        self.parent.fileMenu.insertAction(self.parent.exitAction,
                                          self.exportModuliAction)
        # menubar entry corresponding to sonic widget
        self.menu = menuBar.addMenu('Sonic')
        viewMenu = self.parent.viewMenu
        viewMenu.addSeparator()
        # This action is just a group name and is not connected to any event
        # (disabled)
        # Set the font bold
        separatorGroupTitleAction = QtGui.QAction('Sonic', self.parent)
        font = separatorGroupTitleAction.font()
        font.setBold(True)
        separatorGroupTitleAction.setFont(font)
        viewMenu.addAction(separatorGroupTitleAction)
        separatorGroupTitleAction.setDisabled(True)

        self.modeMenu = viewMenu.addMenu('Mode')
        self.transformMenu = self.menu.addMenu('Transform')
        self.intMenu = self.menu.addMenu('Interpretation')
        self.activeWaveMenu = viewMenu.addMenu('Show waves')

        # VIEW MENU
        viewMenu.addAction(self.autoScaleAction)
        viewMenu.addAction(self.showArrivalsAction)
        # viewMenu.addAction(self.showTableAction)
        # viewMenu.addAction(self.editGradientsAction)
        viewMenu.addAction(self.invertYAction)

        # y axis menu
        self.yAxisMenu = viewMenu.addMenu('y axis')
        self.yAxisMenu.addAction(self.yAxisActions[TRACK_NUMBER_LABEL])

        # MODE MENU
        self.modeMenu.addAction(self.waveFormAction)
        self.modeMenu.addAction(self.contourAction)

        # INTERPRETATION MENU
        # self.intMenu.addAction(self.pickArrivalsAction)
        self.intMenu.addAction(self.shapeArrivalsAction)
        self.intMenu.addAction(self.moduliAction)

        # TRANSFORM MENU
        self.transformMenu.addAction(self.showFFTMagnitudeAction)
        self.transformMenu.addAction(self.showFFTPhaseAction)
        # self.transformMenu.addAction(self.filteringAction)

        # Show waves menu
        self.activeWaveMenu.addAction(self.pWaveAction)
        self.activeWaveMenu.addAction(self.sxWaveAction)
        self.activeWaveMenu.addAction(self.syWaveAction)

        viewMenu.addSeparator()


    def bindData(self):
        '''
        bind wave tracks to the time of experiment the were measured.
        it essentially implies parsing comments and comparing it to sonic data
        names
        Algorithm:
        - find times for non-empty comments
        - throw out repeated comments (take last occurrence)
        - compare comments with sonic file names
        Result:
        times - when waves were recorded
        geo_indices - indices of times in geomechanical dataset
        indices - indices of wave forms to be truncated
        '''
        logger.info('Binding sonic data')
        self.current_data_set = self.parent.currentDataSetName
        # times are when sonic waves were recorded
        self.times = {}
        self.indices = {}   #
        self.geo_indices = {}

        comments = self.parent.comments
        geo_times = self.parent.findData(self.parent.timeParam)

        # filter out empty comments
        non_empty = [i for i, c in enumerate(comments) if c != b'' and c!='']
        comments = comments[non_empty]
        filtered_times = geo_times[non_empty]

        # check if there are any duplicates
        comments, ind = remove_duplicates(comments)
        filtered_times = filtered_times[ind]
        # idk why but these values are not sorted yet
        # but they should be
        filtered_times.sort()

        # find same strings in sonic file names
        for wave in WAVE_TYPES:
            wave_files = list(self.sonicViewer.data[wave].keys())
            # natural keys is a function from lib.functions
            # wave_files.sort(key=natural_keys)
            indices = compare_arrays(comments, wave_files)
            # which items wave_keys are not in comments
            spurious_entries = array_diff(wave_files, comments)
            for e in spurious_entries:
                del self.sonicViewer.data[wave][wave_files[e]]

            # this is what we really need
            self.times[wave] = filtered_times[indices]
            self.indices[wave] = np.arange(len(filtered_times[indices]))
            self.geo_indices[wave] = compare_arrays(geo_times, self.times[wave])

        # rebuild sonic table
        if spurious_entries != []:
            self.sonicViewer.createTable()

        self.sonicViewer.setIndices(self.indices, self.geo_indices)

        # we don't need those anymore
        self.sonicViewer.data = {}

        # set initial length for moduli calculation
        length = float(self.parent.props['length'])
        self.interpretationSettings.lengthLine.setValue(length)

    def truncateData(self):
        '''
        When slider is moved, truncate sonic data
        '''
        interval = self.parent.slider.interval()
        indices = {}
        geo_indices = {}
        for wave in WAVE_TYPES:
            times = self.times[wave]
            mask = ((times >= interval[0]) & (times <= interval[1]))
            indices[wave] = self.indices[wave][mask]
            geo_indices[wave] = self.geo_indices[wave][mask]
            tt = self.parent.findData(self.parent.timeParam)

        self.sonicViewer.setIndices(indices, geo_indices)
        self.sonicViewer.plot()

    def activeWaves(self):
        '''
        wave plots that are currently shown in the widget
        return which buttons are checked
        '''
        active = []
        if self.pWaveAction.isChecked():
            active.append('P')
        if self.sxWaveAction.isChecked():
            active.append('Sx')
        if self.syWaveAction.isChecked():
            active.append('Sy')
        return active

    def connectActions(self):
        self.parent.slider.sigRangeChanged.connect(self.truncateData)
        self.parent.slider.sigRangeChanged.connect(self.moduliWidget.plot)
        self.contourAction.triggered.connect(self.setViewerMode)
        self.waveFormAction.triggered.connect(self.setViewerMode)
        self.pWaveAction.triggered.connect(self.sonicViewer.togglePlotVisibility)
        self.sxWaveAction.triggered.connect(self.sonicViewer.togglePlotVisibility)
        self.syWaveAction.triggered.connect(self.sonicViewer.togglePlotVisibility)
        self.shapeArrivalsAction.triggered.connect(self.activateShapePicking)
        self.showArrivalsAction.triggered.connect(self.sonicViewer.plot)
        self.exportArrivalsAction.triggered.connect(self.raiseExportArrivalDialog)
        self.exportModuliAction.triggered.connect(self.raiseExportModuliDialog)
        self.moduliAction.triggered.connect(self.interpretationSettings.show)
        self.invertYAction.triggered.connect(self.sonicViewer.plot)
        self.autoScaleAction.triggered.connect(self.sonicViewer.autoScalePlots)
        self.showFFTMagnitudeAction.triggered.connect(self.sonicViewer.showFFTAmplitude)
        self.showFFTPhaseAction.triggered.connect(self.sonicViewer.showFFTPhases)

    def raiseExportModuliDialog(self):
        lastdir = str(self.parent.checkForLastDir())  # convert normal string
        fname, filter = QtGui.QFileDialog.getSaveFileName(self.parent, "",
                                                          lastdir, "*.csv")
        if (fname):
            self.exportModuli(fname)
        else:
            logger.debug("File name not set")

    def raiseExportArrivalDialog(self):
        lastdir = str(self.parent.checkForLastDir())  # convert normal string
        fname, filter = QtGui.QFileDialog.getSaveFileName(self.parent, "",
                                                          lastdir, "*.csv")
        if (fname):
            self.exportArrivals(fname)
        else:
            logger.debug("File name not set")

    def exportModuli(self, fname):
        logger.info('Saving moduli to %s'%(fname))
        data = []
        keys = []
        # get experimental plot parameter
        keys.append(self.moduliWidget.parameter())
        data.append(self.moduliWidget.getGeoArray())
        # get moduli
        mod = self.moduliWidget.getActiveModuli()
        for key in mod.keys():
            keys.append(key)
            data.append(mod[key])
        write_csv(keys, data, fname)

    def exportArrivals(self, fname):
        logger.info('Saving arrivals to %s'%(fname))
        data = []
        keys = []
        sv = self.sonicViewer
        for k, wave in enumerate(sv.getActivePlots()):
            if wave in sv.arrival_times.keys():
                keys.append("time_" + wave)
                keys.append(wave)
                arrivals = sv.arrival_times[wave][sv.indices[wave]]
                exp_times = self.sonicViewer.getYArray(wave)
                data.append(exp_times)
                data.append(arrivals)
        write_csv(keys, data, fname)

    def activateShapePicking(self):
        active_waves = self.activeWaves()
        self.sonicViewer.plotWidget.showROIs(active_waves)
        for wave in active_waves:
            plt = self.sonicViewer.plots[wave]
            roi = self.sonicViewer.plotWidget.rois[wave]
            n_points = len(roi.getState()['points'])
            if n_points == 2:   # scale initially
                view_range = plt.viewRange()
                x = (view_range[0][0] + view_range[0][1])/2
                range_y = [view_range[1][0], view_range[1][1]]
                roi.setPoints([(x, range_y[0]), (x, range_y[1])])

        self.shapeControlWidget = ShapeControlWidget(parent=self.sonicViewer)

    def setViewerMode(self):
        if self.waveFormAction.isChecked():
            mode = VIEW_MODES[1]
        elif self.contourAction.isChecked():
            mode = VIEW_MODES[0]

        self.sonicViewer.setMode(mode)
        self.setYParameters()
        self.sonicViewer.plot()

    def createYActions(self):
        self.yAxisActions[TRACK_NUMBER_LABEL] = QtGui.QAction(
            TRACK_NUMBER_LABEL, self.parent,
            checkable=True)
        self.yAxisActions[TRACK_NUMBER_LABEL].setActionGroup(self.yAxisGroup)
        for p in self.parent.keys:
            self.yAxisActions[p] = QtGui.QAction(p, self.parent, checkable=True)
            self.yAxisActions[p].setActionGroup(self.yAxisGroup)
        self.connectYAxisActions()

    def setYParameters(self):
        default_active_action = self.parent.timeParam
        mode = self.sonicViewer.mode
        assert mode in VIEW_MODES
        last_active_action = self.yAxisGroup.checkedAction()
        self.yAxisMenu.clear()
        if mode == VIEW_MODES[0]:    # contours
            assert self.parent.timeParam in self.yAxisActions.keys()
            self.yAxisMenu.addAction(self.yAxisActions[self.parent.timeParam])
            self.yAxisMenu.addAction(self.yAxisActions[TRACK_NUMBER_LABEL])

        elif mode == VIEW_MODES[1]:  # wave forms
            for key, action in self.yAxisActions.items():
                self.yAxisMenu.addAction(action)
            if last_active_action is not None:
                default_active_action = last_active_action.text()

        try:
            logger.info('Setting y axis to: %s'%(default_active_action))
            self.yAxisActions[default_active_action].setChecked(True)
        except: logger.warning('setting was not successful')

    def connectYAxisActions(self):
        for key, action in self.yAxisActions.items():
            action.triggered.connect(self.sonicViewer.plot)

    def setEnabled(self, enabled=True):
        '''
        Block the tab corresponding to the sonic plugin
        and disable sonic viewer from doing anything
        '''
        tab_index = self.parent.tabWidget.indexOf(self.sonicViewer)
        self.parent.tabWidget.setTabEnabled(tab_index, enabled)
        self.sonicViewer.setEnabled(enabled)
        if enabled:
            self.parent.tabWidget.setCurrentWidget(self.sonicViewer)
            if self.sonicViewer.arrivalsPicked:
                self.exportArrivalsAction.setEnabled(True)
                self.exportModuliAction.setEnabled(True)
            else:
                self.exportArrivalsAction.setEnabled(False)
                self.exportModuliAction.setEnabled(False)

        # also disable  moduli widget (it's enabled only when ran)
        if not enabled:
            tab_index = self.parent.tabWidget.indexOf(self.moduliWidget)
            # maybe i should remove/block this widget tab?
            self.parent.tabWidget.setTabEnabled(tab_index, False)
            self.sonicViewer.setEnabled(False)
            self.exportArrivalsAction.setEnabled(False)
            self.exportModuliAction.setEnabled(False)
            self.sonicViewer.fftWidget.close()

        # enable/block actions/menus
        self.autoScaleAction.setEnabled(enabled)
        self.modeMenu.setEnabled(enabled)
        self.activeWaveMenu.setEnabled(enabled)
        self.invertYAction.setEnabled(enabled)
        self.yAxisMenu.setEnabled(enabled)
        self.menu.setEnabled(enabled)

    def runModuliWidget(self):
        '''
        Add moduli widget as a tab.
        Run widget that computes static and dynamic moduli and plots them
        together
        '''
        # first add the widget as a tab
        tab_index = self.parent.tabWidget.indexOf(self.moduliWidget)
        if tab_index == -1:
            self.parent.tabWidget.addTab(self.moduliWidget, "Moduli")
        self.parent.tabWidget.setCurrentWidget(self.moduliWidget)
        self.parent.tabWidget.setTabEnabled(tab_index, True)
        # now set config
        testconf = self.interpretationSettings.testconf
        capsconf = self.interpretationSettings.capsconf
        if testconf == None: return 0
        dens = self.interpretationSettings.dens
        length = self.interpretationSettings.length
        atime = self.interpretationSettings.atime
        self.moduliWidget.setConfig(testconf, capsconf, dens, length, atime)
        # finally run the widget
        self.moduliWidget.setEnabled()
        self.moduliWidget.run()
