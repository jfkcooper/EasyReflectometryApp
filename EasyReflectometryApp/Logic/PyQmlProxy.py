# noqa: E501
from cmath import log
import os
import sys
import pathlib
import datetime
import re
import timeit
import json
from typing import Union
from dicttoxml import dicttoxml

from PySide2.QtCore import QObject, Slot, Signal, Property
from PySide2.QtCore import QByteArray, QBuffer, QIODevice

from easyCore import np, borg
from easyCore.Objects.Groups import BaseCollection
from easyCore.Objects.Base import BaseObj
from easyCore.Fitting.Fitting import Fitter
from easyCore.Utils.UndoRedo import property_stack_deco

from easyAppLogic.Utils.Utils import generalizePath

from EasyReflectometry.sample.material import Material
from EasyReflectometry.sample.materials import Materials
from EasyReflectometry.sample.layer import Layer
from EasyReflectometry.sample.layers import Layers
from EasyReflectometry.sample.item import MultiLayer, RepeatingMultiLayer
from EasyReflectometry.experiment.model import Model
from EasyReflectometry.interface import InterfaceFactory


from .Project import ProjectProxy
from .Simulation import SimulationProxy
from .Material import MaterialProxy
from .Model import ModelProxy
from .Calculator import CalculatorProxy
from .Parameter import ParameterProxy
from .Data import DataProxy

from .DataStore import DataSet1D, DataStore
from .Proxies.Plotting1d import Plotting1dProxy
from .Fitter import Fitter as ThreadedFitter

ITEM_LOOKUP = {
                'Multi-layer': MultiLayer,
                'Repeating Multi-layer': RepeatingMultiLayer
              }

class PyQmlProxy(QObject):
    # SIGNALS
    parametersChanged = Signal()
    
    statusInfoChanged = Signal()
    dummySignal = Signal()

    # Project
    projectCreatedChanged = Signal()
    projectInfoChanged = Signal()
    stateChanged = Signal(bool)

    # Items
    sampleChanged = Signal()
    
    currentSampleChanged = Signal()

    experimentDataAdded = Signal()
    experimentDataRemoved = Signal()

    fitFinished = Signal()
    fitFinishedNotify = Signal()
    fitResultsChanged = Signal()
    stopFit = Signal()

    currentMinimizerChanged = Signal()
    currentMinimizerMethodChanged = Signal()


    # Plotting
    showMeasuredSeriesChanged = Signal()
    showDifferenceChartChanged = Signal()
    current1dPlottingLibChanged = Signal()

    htmlExportingFinished = Signal(bool, str) 

    # Undo Redo
    undoRedoChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
            
        # Main
        self._interface = InterfaceFactory()

        ######### proxies #########
        self._simulation_proxy = SimulationProxy(self)
        self._material_proxy = MaterialProxy(self)
        self._model_proxy = ModelProxy(self)
        self._calculator_proxy = CalculatorProxy(self)
        self._parameter_proxy = ParameterProxy(self)
        self._data_proxy = DataProxy(self)

        # Plotting 1D
        self._plotting_1d_proxy = Plotting1dProxy()

        # Project
        self._project_created = False
        self._project_info = self._defaultProjectInfo()
        self.project_save_filepath = ""
        self._status_model = None
        self._state_changed = False
        self.stateChanged.connect(self._onStateChanged)

        # Materials
        self._current_materials_index = 1
        self._current_materials_len = len(self._material_proxy._materials)
        self.sampleChanged.connect(self._material_proxy._onMaterialsChanged)
        self.currentSampleChanged.connect(self._onCurrentMaterialsChanged)

        # Layers
        self._current_layers_index = 1

        # Items
        self._current_items_index = 1
        self.sampleChanged.connect(self._model_proxy._onModelChanged)
        self.currentSampleChanged.connect(self._onCurrentItemsChanged)

        # Experiment
        self._experiment_data = None
        self.experiments = []
        self.experimentDataAdded.connect(self._simulation_proxy._onExperimentDataAdded)
        self.experimentDataRemoved.connect(self._onExperimentDataRemoved)

        # Analysis

        self.sampleChanged.connect(self._simulation_proxy._onSimulationParametersChanged)
        self.sampleChanged.connect(self._parameter_proxy._onParametersChanged)
        self._simulation_proxy.simulationParametersChanged.connect(self.undoRedoChanged)
        self._simulation_proxy.backgroundChanged.connect(self.undoRedoChanged)
        self._simulation_proxy.qRangeChanged.connect(self.undoRedoChanged)
        self._simulation_proxy.resolutionChanged.connect(self.undoRedoChanged)

        self._fit_results = self._defaultFitResults()
        self.fitter = Fitter(self._model_proxy._model, self._interface.fit_func)
        self.fitFinished.connect(self._onFitFinished)

        self._current_minimizer_method_index = 0
        self._current_minimizer_method_name = self.fitter.available_methods()[0]
        self.currentMinimizerChanged.connect(self._onCurrentMinimizerChanged)
        self.currentMinimizerMethodChanged.connect(self._onCurrentMinimizerMethodChanged)

        # Parameters
        self.parametersChanged.connect(self._material_proxy._onMaterialsChanged)
        self.parametersChanged.connect(self._model_proxy._onModelChanged)
        self.parametersChanged.connect(self._simulation_proxy._onSimulationParametersChanged)
        self.parametersChanged.connect(self._parameter_proxy._onParametersChanged)
        self.parametersChanged.connect(self._simulation_proxy._onCalculatedDataChanged)
        self.parametersChanged.connect(self.undoRedoChanged)

        # Report
        self._report = ""

        # Status info
        self.statusInfoChanged.connect(self._onStatusInfoChanged)
        self._calculator_proxy.calculatorChanged.connect(self.statusInfoChanged)
        #self._calculator_proxy.calculatorChanged.connect(self.undoRedoChanged)
        self.currentMinimizerChanged.connect(self.statusInfoChanged)
        #self.currentMinimizerChanged.connect(self.undoRedoChanged)
        self.currentMinimizerMethodChanged.connect(self.statusInfoChanged)
        #self.currentMinimizerMethodChanged.connect(self.undoRedoChanged)

        # Multithreading
        self._fitter_thread = None
        self._fit_finished = True
        self.stopFit.connect(self.onStopFit)

        # Multithreading
        self._fitter_thread = None
        self._fit_finished = True

        # Screen recorder
        recorder = None
        try:
            from EasyReflectometryApp.Logic.ScreenRecorder import ScreenRecorder
            recorder = ScreenRecorder()
        except (ImportError, ModuleNotFoundError):
            print('Screen recording disabled')
        self._screen_recorder = recorder

        # !! THIS SHOULD ALWAYS GO AT THE END !!
        # Start the undo/redo stack
        borg.stack.enabled = True
        borg.stack.clear()
        # borg.debug = True

        self._currentProjectPath = os.path.expanduser("~")
        self._material_proxy._onMaterialsChanged()
        self._model_proxy._onModelChanged()

    @Property('QVariant', notify=dummySignal)
    def simulation(self):
        return self._simulation_proxy

    @Property('QVariant', notify=dummySignal)
    def material(self):
        return self._material_proxy

    @Property('QVariant', notify=dummySignal)
    def model(self):
        return self._model_proxy

    @Property('QVariant', notify=dummySignal)
    def calculator(self):
        return self._calculator_proxy

    @Property('QVariant', notify=dummySignal)
    def parameter(self):
        return self._parameter_proxy

    @Property('QVariant', notify=dummySignal)
    def data(self):
        return self._data_proxy

    ####################################################################################################################
    ####################################################################################################################
    # Charts
    ####################################################################################################################
    ####################################################################################################################

    # 1d plotting

    @Property('QVariant', notify=dummySignal)
    def plotting1d(self):
        return self._plotting_1d_proxy

    # Charts for report

    @Slot('QVariant', result=str)
    def imageToSource(self, image):
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, 'png')
        data = ba.toBase64().data().decode('utf-8')
        source = f'data:image/png;base64,{data}'
        return source

    ####################################################################################################################
    ####################################################################################################################
    # PROJECT
    ####################################################################################################################
    ####################################################################################################################

    ####################################################################################################################
    # Project
    ####################################################################################################################

    @Property('QVariant', notify=projectInfoChanged)
    def projectInfoAsJson(self):
        return self._project_info

    @projectInfoAsJson.setter
    def projectInfoAsJson(self, json_str):
        self._project_info = json.loads(json_str)
        self.projectInfoChanged.emit()

    @Property(str, notify=projectInfoChanged)
    def projectInfoAsCif(self):
        cif_list = []
        for key, value in self.projectInfoAsJson.items():
            if ' ' in value:
                value = f"'{value}'"
            cif_list.append(f'_{key} {value}')
        cif_str = '\n'.join(cif_list)
        return cif_str

    @Slot(str, str)
    def editProjectInfo(self, key, value):
        if key == 'location':
            self.currentProjectPath = value
            return
        else:
            if self._project_info[key] == value:
                return
            self._project_info[key] = value
        self.projectInfoChanged.emit()

    @Property(str, notify=projectInfoChanged)
    def currentProjectPath(self):
        return self._currentProjectPath

    @currentProjectPath.setter
    def currentProjectPath(self, new_path):
        if self._currentProjectPath == new_path:
            return
        self._currentProjectPath = new_path
        self.projectInfoChanged.emit()

    @Slot()
    def createProject(self):
        projectPath = self.currentProjectPath #self.projectInfoAsJson['location']
        mainCif = os.path.join(projectPath, 'project.cif')
        samplesPath = os.path.join(projectPath, 'samples')
        experimentsPath = os.path.join(projectPath, 'experiments')
        calculationsPath = os.path.join(projectPath, 'calculations')
        if not os.path.exists(projectPath):
            os.makedirs(projectPath)
            os.makedirs(samplesPath)
            os.makedirs(experimentsPath)
            os.makedirs(calculationsPath)
            with open(mainCif, 'w') as file:
                file.write(self.projectInfoAsCif)
        else:
            print(f"ERROR: Directory {projectPath} already exists")

    def _defaultProjectInfo(self):
        return dict(
            name="Example Project",
            # location=os.path.join(os.path.expanduser("~"), "Example Project"),
            short_description="reflectometry, 1D",
            samples="Not loaded",
            experiments="Not loaded",
            modified=datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        )

    @Property(bool, notify=stateChanged)
    def stateHasChanged(self):
        return self._state_changed

    @stateHasChanged.setter
    def stateHasChanged(self, changed: bool):
        if self._state_changed == changed:
            print("same state changed value - {}".format(str(changed)))
            return
        self._state_changed = changed
        print("new state changed value - {}".format(str(changed)))
        self.stateChanged.emit(changed)

    def _onStateChanged(self, changed=True):
        self.stateHasChanged = changed

    ####################################################################################################################
    # Current Materials
    ####################################################################################################################

    @Property(int, notify=currentSampleChanged)
    def currentMaterialsIndex(self):
        return self._current_materials_index

    @currentMaterialsIndex.setter
    def currentMaterialsIndex(self, new_index: int):
        if self._current_materials_index == new_index or new_index == -1:
            return
        self._current_materials_index = new_index
        self.sampleChanged.emit()

    def _onCurrentMaterialsChanged(self):
        self.sampleChanged.emit()
        
    ####################################################################################################################
    # Current Items
    ####################################################################################################################

    @Property(int, notify=currentSampleChanged)
    def currentItemsIndex(self):
        print('**currentItemsIndex')
        return self._current_items_index

    @currentItemsIndex.setter
    def currentItemsIndex(self, new_index: int):
        print('**currentItemsIndexSetter')
        if self._current_items_index == new_index or new_index == -1:
            return
        self._current_items_index = new_index
        self.sampleChanged.emit()

    @Property(int, notify=currentSampleChanged)
    def currentItemsRepetitions(self):
        print('**currentItemsRepetitions')
        if self._model_proxy._model.structure[self.currentItemsIndex].type != 'Repeating Multi-layer':
            return 1
        return self._model_proxy._model.structure[self.currentItemsIndex].repetitions.raw_value

    @currentItemsRepetitions.setter
    def currentItemsRepetitions(self, new_repetitions: int):
        print('**currentItemsRepetitionsSetter')
        if self._model_proxy._model.structure[self.currentItemsIndex].type != 'Repeating Multi-layer':
            return
        if self._model_proxy._model.structure[self.currentItemsIndex].repetitions.raw_value == new_repetitions or new_repetitions == -1:
            return
        self._model_proxy._model.structure[self.currentItemsIndex].repetitions = new_repetitions
        self.sampleChanged.emit()

    @Property(str, notify=currentSampleChanged)
    def currentItemsType(self):
        print('**currentItemsType')
        return self._model_proxy._model.structure[self.currentItemsIndex].type

    @currentItemsType.setter
    def currentItemsType(self, type: str):
        print('**ccurrentItemsTypeSetter')
        if self._model_proxy._model.structure[self.currentItemsIndex].type == type or type == -1:
            return
        current_layers = self._model_proxy._model.structure[self.currentItemsIndex].layers
        current_name = self._model_proxy._model.structure[self.currentItemsIndex].name
        target_position = self.currentItemsIndex
        self._model_proxy._model.remove_item(self.currentItemsIndex)
        if type == 'Multi-layer':
            self._model_proxy._model.add_item(ITEM_LOOKUP[type].from_pars(
                current_layers, current_name))
        elif type == 'Repeating Multi-layer':
            self._model_proxy._model.add_item(ITEM_LOOKUP[type].from_pars(
                current_layers, 1, current_name))
        if target_position != len(self._model_proxy._model.structure) - 1:
            new_items_list = []
            self._model_proxy._model.structure[0].layers[0].thickness.enabled = True
            self._model_proxy._model.structure[0].layers[0].roughness.enabled = True
            self._model_proxy._model.structure[-1].layers[-1].thickness.enabled = True
            for i, item in enumerate(self._model_proxy._model.structure):
                if i == target_position:
                    new_items_list.append(self._model_proxy._model.structure[len(self._model_proxy._model.structure) - 1])
                elif i == len(self._model_proxy._model.structure) - 1:
                    new_items_list.append(self._model_proxy._model.structure[target_position])
                else:
                    new_items_list.append(item)
            while len(self._model_proxy._model.structure) != 0:
                self._model_proxy._model.remove_item(0)
            for i in range(len(new_items_list)):
                self._model_proxy._model.add_item(new_items_list[i])
            borg.stack.enabled = True
            self._model_proxy._model.structure[0].layers[0].thickness.enabled = False
            self._model_proxy._model.structure[0].layers[0].roughness.enabled = False
            self._model_proxy._model.structure[-1].layers[-1].thickness.enabled = False
        self.sampleChanged.emit()

    def _onCurrentItemsChanged(self):
        self.sampleChanged.emit()

    ####################################################################################################################
    # Current Layers
    ####################################################################################################################
 
    @Property(int, notify=currentSampleChanged)
    def currentLayersIndex(self):
        return self._current_layers_index

    @currentLayersIndex.setter
    def currentLayersIndex(self, new_index: int):
        if self._current_layers_index == new_index or new_index == -1:
            return
        self._current_layers_index = new_index
        self.sampleChanged.emit()

    ####################################################################################################################
    # Experiment data: Add / Remove
    ####################################################################################################################

    @Slot(str)
    def addExperimentDataFromOrt(self, file_url):
        print(f"+ addExperimentDataFromOrt: {file_url}")

        self._experiment_data = self._loadExperimentData(file_url)
        self._data_proxy._data.experiments[0].name = pathlib.Path(file_url).stem
        self.experiments = [{'name': experiment.name} for experiment in self._data_proxy._data.experiments]
        self._data_proxy.experimentLoaded = True
        self._data_proxy.experimentSkipped = False
        self.experimentDataAdded.emit()

    @Slot()
    def removeExperiment(self):
        print("+ removeExperiment")
        self.experiments.clear()
        self._data_proxy.experimentLoaded = False
        self._data_proxy.experimentSkipped = False
        self.experimentDataRemoved.emit()

    def _loadExperimentData(self, file_url):
        print("+ _loadExperimentData")
        file_path = generalizePath(file_url)
        data = self._data_proxy._data.experiments[0]
        try:
            data.x, data.y, data.ye, data.xe = np.loadtxt(file_path, unpack=True)
        except ValueError:
            data.x, data.y, data.ye = np.loadtxt(file_path, unpack=True)
        return data

    def _onExperimentDataRemoved(self):
        print("***** _onExperimentDataRemoved")
        self._plotting_1d_proxy.clearFrontendState()
        self._data_proxy.experimentDataAsObjChanged.emit()

    @Slot(str)
    def setCurrentExperimentDatasetName(self, name):
        if self._data_proxy._data.experiments[0].name == name:
            return

        self._data_proxy._data.experiments[0].name = name
        self._data_proxy.experimentDataAsObjChanged.emit()
        self.projectInfoAsJson['experiments'] = name
        self.projectInfoChanged.emit()


    ####################################################################################################################
    ####################################################################################################################
    # ANALYSIS
    ####################################################################################################################
    ####################################################################################################################

    ####################################################################################################################
    # Minimizer
    ####################################################################################################################

    # Minimizer

    @Property('QVariant', notify=dummySignal)
    def minimizerNames(self):
        return self.fitter.available_engines

    @Property(int, notify=currentMinimizerChanged)
    def currentMinimizerIndex(self):
        current_name = self.fitter.current_engine.name
        return self.minimizerNames.index(current_name)

    @currentMinimizerIndex.setter
    @property_stack_deco('Minimizer change')
    def currentMinimizerIndex(self, new_index: int):
        if self.currentMinimizerIndex == new_index:
            return
        new_name = self.minimizerNames[new_index]
        self.fitter.switch_engine(new_name)
        self.currentMinimizerChanged.emit()

    # @Slot(int)
    # def changeCurrentMinimizer(self, new_index: int):
    #     if self.currentMinimizerIndex == new_index:
    #         return
    #
    #     new_name = self.minimizerNames[new_index]
    #     self.fitter.switch_engine(new_name)
    #     self.currentMinimizerChanged.emit()

    def _onCurrentMinimizerChanged(self):
        print("***** _onCurrentMinimizerChanged")
        idx = 0
        minimizer_name = self.fitter.current_engine.name
        if minimizer_name == 'lmfit':
            idx = self.minimizerMethodNames.index('leastsq')
        elif minimizer_name == 'bumps':
            idx = self.minimizerMethodNames.index('lm')
        if -1 < idx != self._current_minimizer_method_index:
            # Bypass the property as it would be added to the stack.
            self._current_minimizer_method_index = idx
            self._current_minimizer_method_name = self.minimizerMethodNames[idx]
            self.currentMinimizerMethodChanged.emit()

    # Minimizer method

    @Property('QVariant', notify=currentMinimizerChanged)
    def minimizerMethodNames(self):
        current_minimizer = self.minimizerNames[self.currentMinimizerIndex]
        tested_methods = {
            'lmfit': ['leastsq', 'powell', 'cobyla'],
            'bumps': ['newton', 'lm', 'de'],
            'DFO_LS': ['leastsq']
        }
        #return self.fitter.available_methods()
        return tested_methods[current_minimizer]

    @Property(int, notify=currentMinimizerMethodChanged)
    def currentMinimizerMethodIndex(self):
        return self._current_minimizer_method_index

    @currentMinimizerMethodIndex.setter
    @property_stack_deco('Minimizer method change')
    def currentMinimizerMethodIndex(self, new_index: int):
        if self._current_minimizer_method_index == new_index:
            return

        self._current_minimizer_method_index = new_index
        self._current_minimizer_method_name = self.minimizerMethodNames[new_index]
        self.currentMinimizerMethodChanged.emit()

    def _onCurrentMinimizerMethodChanged(self):
        print("***** _onCurrentMinimizerMethodChanged")

    ####################################################################################################################
    # Fitting
    ####################################################################################################################

    @Slot()
    def fit(self):
        # if running, stop the thread
        if not self.isFitFinished:
            self.onStopFit()
            borg.stack.endMacro()  # need this to close the undo stack properly
            return
        # macos is possibly problematic with MT, skip on this platform
        if 'darwin' in sys.platform:
            self.nonthreaded_fit()
        else:
            self.threaded_fit()

    def nonthreaded_fit(self):
        self.isFitFinished = False
        exp_data = self._data_proxy._data.experiments[0]

        x = exp_data.x
        y = exp_data.y
        weights = 1 / exp_data.ye
        method = self._current_minimizer_method_name

        res = self.fitter.fit(x, y, weights=weights, method=method)
        self._setFitResults(res)

    def threaded_fit(self):
        self.isFitFinished = False
        exp_data = self._data_proxy._data.experiments[0]

        x = exp_data.x
        y = exp_data.y
        weights = 1 / exp_data.ye
        method = self._current_minimizer_method_name

        args = (x, y)
        kwargs = {"weights": weights, "method": method}
        self._fitter_thread = ThreadedFitter(self, self.fitter, 'fit', *args, **kwargs)
        self._fitter_thread.setTerminationEnabled(True)
        self._fitter_thread.finished.connect(self._setFitResults)
        self._fitter_thread.failed.connect(self._setFitResultsFailed)
        self._fitter_thread.start()

    def onStopFit(self):
        """
        Slot for thread cancelling and reloading parameters
        """
        self.stop_fit()
        self._fitter_thread = None

        self._fit_results['success'] = 'cancelled'
        self._fit_results['nvarys'] = None
        self._fit_results['GOF'] = None
        self._fit_results['redchi2'] = None
        self._setFitResultsFailed("Fitting stopped")

    def stop_fit(self):
        self._fitter_thread.stop()

    @Property('QVariant', notify=fitResultsChanged)
    def fitResults(self):
        return self._fit_results

    @Property(bool, notify=fitFinishedNotify)
    def isFitFinished(self):
        return self._fit_finished

    @isFitFinished.setter
    def isFitFinished(self, fit_finished: bool):
        if self._fit_finished == fit_finished:
            return
        self._fit_finished = fit_finished
        self.fitFinishedNotify.emit()

    def _defaultFitResults(self):
        return {
            "success": None,
            "nvarys":  None,
            "GOF":     None,
            "redchi2": None
        }

    def _setFitResults(self, res):
        self._fit_results = {
            "success": res.success,
            "nvarys":  res.n_pars,
            "GOF":     float(res.goodness_of_fit),
            "redchi2": float(res.reduced_chi)
        }
        self.fitResultsChanged.emit()
        self.isFitFinished = True
        self.fitFinished.emit()

    def _setFitResultsFailed(self, res):
        self.isFitFinished = True

    def _onFitFinished(self):
        self.parametersChanged.emit()

    ####################################################################################################################
    ####################################################################################################################
    # Report
    ####################################################################################################################
    ####################################################################################################################

    @Slot(str)
    def setReport(self, report):
        """
        Keep the QML generated HTML report for saving
        """
        self._report = report

    @Slot(str)
    def saveReport(self, filepath):
        """
        Save the generated report to the specified file
        Currently only html
        """
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(self._report)
            success = True
        except IOError:
            success = False
        finally:
            self.htmlExportingFinished.emit(success, filepath)

    ####################################################################################################################
    ####################################################################################################################
    # STATUS
    ####################################################################################################################
    ####################################################################################################################

    @Property('QVariant', notify=statusInfoChanged)
    def statusModelAsObj(self):
        obj = {
            "calculation":  self._interface.current_interface_name,
            "minimization": f'{self.fitter.current_engine.name} ({self._current_minimizer_method_name})'
        }
        self._status_model = obj
        return obj

    @Property(str, notify=statusInfoChanged)
    def statusModelAsXml(self):
        model = [
            {"label": "Calculation", "value": self._interface.current_interface_name},
            {"label": "Minimization",
             "value": f'{self.fitter.current_engine.name} ({self._current_minimizer_method_name})'}
        ]
        xml = dicttoxml(model, attr_type=False)
        xml = xml.decode()
        return xml

    def _onStatusInfoChanged(self):
        print("***** _onStatusInfoChanged")


    ####################################################################################################################
    ####################################################################################################################
    # Screen recorder
    ####################################################################################################################
    ####################################################################################################################

    @Property('QVariant', notify=dummySignal)
    def screenRecorder(self):
        return self._screen_recorder

    ####################################################################################################################
    ####################################################################################################################
    # State save/load
    ####################################################################################################################
    ####################################################################################################################

    @Slot()
    def saveProject(self):
        self._saveProject()
        self.stateChanged.emit(False)

    @Slot(str)
    def loadProjectAs(self, filepath):
        self._loadProjectAs(filepath)
        self.stateChanged.emit(False)

    @Slot()
    def loadProject(self):
        self._loadProject()
        self.stateChanged.emit(False)

    @Slot(str)
    def loadExampleProject(self, filepath):
        self._loadProjectAs(filepath)
        self.currentProjectPath = '--- EXAMPLE ---'
        self.stateChanged.emit(False)

    @Property(str, notify=dummySignal)
    def projectFilePath(self):
        return self.project_save_filepath

    def _saveProject(self):
        """
        """
        projectPath = self.currentProjectPath
        project_save_filepath = os.path.join(projectPath, 'project.json')
        materials_in_model = []
        for i in self._model_proxy._model.structure:
            for j in i.layers:
                materials_in_model.append(j.material)
        materials_not_in_model = []
        for i in self._material_proxy._materials:
            if i not in materials_in_model:
                materials_not_in_model.append(i)
        descr = {
            'model': self._model_proxy._model.as_dict(skip=['interface']),
            'materials_not_in_model': Materials(*materials_not_in_model).as_dict(skip=['interface'])
        }
        
        if self._data_proxy._data.experiments:
            experiments_x = self._data_proxy._data.experiments[0].x
            experiments_y = self._data_proxy._data.experiments[0].y
            experiments_ye = self._data_proxy._data.experiments[0].ye
            if self._data_proxy._data.experiments[0].xe is not None:
                experiments_xe = self._data_proxy._data.experiments[0].xe
                descr['experiments'] = [experiments_x, experiments_y, experiments_ye, experiments_xe]
            else:
                descr['experiments'] = [experiments_x, experiments_y, experiments_ye]

        descr['experiment_skipped'] = self._data_proxy._experiment_skipped
        descr['project_info'] = self._project_info

        descr['interface'] = self._interface.current_interface_name

        descr['minimizer'] = {
            'engine': self.fitter.current_engine.name,
            'method': self._current_minimizer_method_name
        }

        content_json = json.dumps(descr, indent=4, default=self.default)
        path = generalizePath(project_save_filepath)
        createFile(path, content_json)

    def default(self, obj):
        if type(obj).__module__ == np.__name__:
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            else:
                return obj.item()
        raise TypeError('Unknown type:', type(obj))

    def _loadProjectAs(self, filepath):
        """
        """
        self.project_load_filepath = filepath
        print("LoadProjectAs " + filepath)
        self.loadProject()

    def _loadProject(self):
        """
        """
        path = generalizePath(self.project_load_filepath)
        if not os.path.isfile(path):
            print("Failed to find project: '{0}'".format(path))
            return
        self.currentProjectPath = os.path.split(path)[0]
        with open(path, 'r') as xml_file:
            descr: dict = json.load(xml_file)

        interface_name = descr.get('interface', None)
        if interface_name is not None:
            old_interface_name = self._interface.current_interface_name
            if old_interface_name != interface_name:
                self._interface.switch(interface_name)

        self._model_proxy._model = Model.from_dict(descr['model'])
        for i in self._model_proxy._model.structure:
            for j in i.layers:
                self._material_proxy._materials.append(j.material)
        for i in Materials.from_dict(descr['materials_not_in_model']):
            self._material_proxy._materials.append(i)
        self._model_proxy._model.interface = self._interface
        self.sampleChanged.emit()

        # experiment
        if 'experiments' in descr:
            self._data_proxy.experimentLoaded = True
            self._data_proxy._data.experiments[0].x = np.array(descr['experiments'][0])
            self._data_proxy._data.experiments[0].y = np.array(descr['experiments'][1])
            self._data_proxy._data.experiments[0].ye = np.array(descr['experiments'][2])
            if len(descr['experiments'] == 4):
                self._data_proxy._data.experiments[0].xe = np.array(descr['experiments'][3])
            else:
                self._data_proxy._data.experiments[0].xe = None
            self._experiment_data = self._data_proxy._data.experiments[0]
            self.experiments = [{'name': descr['project_info']['experiments']}]
            self.setCurrentExperimentDatasetName(descr['project_info']['experiments'])
            self._data_proxy.experimentLoaded = True
            self._data_proxy.experimentSkipped = False
            self.experimentDataAdded.emit()
            self._parameter_proxy._onParametersChanged()

        else:
            # delete existing experiment
            self.removeExperiment()
            self._data_proxy.experimentLoaded = False
            if descr['experiment_skipped']:
                self._data_proxy.experimentSkipped = True
                self._data_proxy.experimentSkippedChanged.emit()
            else:
                self._data_proxy.experimentSkipped = False

        # project info
        self.projectInfoAsJson = json.dumps(descr['project_info'])

        new_minimizer_settings = descr.get('minimizer', None)
        if new_minimizer_settings is not None:
            new_engine = new_minimizer_settings['engine']
            new_method = new_minimizer_settings['method']
            new_engine_index = self.minimizerNames.index(new_engine)
            self.currentMinimizerIndex = new_engine_index
            new_method_index = self.minimizerMethodNames.index(new_method)
            self.currentMinimizerMethodIndex = new_method_index

        self.fitter.fit_object = self._model_proxy._model

        self.resetUndoRedoStack()

        self.projectCreated = True

    ####################################################################################################################
    # Undo/Redo stack operations
    ####################################################################################################################

    @Property(bool, notify=undoRedoChanged)
    def canUndo(self) -> bool:
        return borg.stack.canUndo()

    @Property(bool, notify=undoRedoChanged)
    def canRedo(self) -> bool:
        return borg.stack.canRedo()

    @Slot()
    def undo(self):
        if self.canUndo:
            callback = [self.parametersChanged]
            if len(borg.stack.history[0]) > 1:
                callback = [self.phaseAdded, self.parametersChanged]
            else:
                old = borg.stack.history[0].current._parent
                if isinstance(old, (BaseObj, BaseCollection)):
                    if isinstance(old, (Phase, Phases)):
                        callback = [self.phaseAdded, self.parametersChanged]
                    else:
                        callback = [self.parametersChanged]
                elif old is self:
                    # This is a property of the proxy. I.e. minimizer, minimizer method, name or something boring.
                    # Signals should be sent by triggering the set method.
                    callback = []
                else:
                    print(f'Unknown undo thing: {old}')
            borg.stack.undo()
            _ = [call.emit() for call in callback]

    @Slot()
    def redo(self):
        if self.canRedo:
            callback = [self.parametersChanged]
            if len(borg.stack.future[0]) > 1:
                callback = [self.phaseAdded, self.parametersChanged]
            else:
                new = borg.stack.future[0].current._parent
                if isinstance(new, (BaseObj, BaseCollection)):
                    if isinstance(new, (Phase, Phases)):
                        callback = [self.phaseAdded, self.parametersChanged]
                    else:
                        callback = [self.parametersChanged, self.undoRedoChanged]
                elif new is self:
                    # This is a property of the proxy. I.e. minimizer, minimizer method, name or something boring.
                    # Signals should be sent by triggering the set method.
                    callback = []
                else:
                    print(f'Unknown redo thing: {new}')
            borg.stack.redo()
            _ = [call.emit() for call in callback]

    @Property(str, notify=undoRedoChanged)
    def undoText(self):
        return self.tooltip(borg.stack.undoText())

    @Property(str, notify=undoRedoChanged)
    def redoText(self):
        return self.tooltip(borg.stack.redoText())

    def tooltip(self, orig_tooltip=""):
        if 'Parameter' not in orig_tooltip:
            # if this is not a parameter, print the full undo text
            return orig_tooltip
        pattern = "<Parameter '(.*)': .* from (.*) to (.*)"
        match = re.match(pattern, orig_tooltip)
        if match is None:
           # regex parsing failed, return the original tooltip
            return orig_tooltip
        param = match.group(1)
        frm = match.group(2)
        if '+/-' in frm:
            # numerical values
            pattern2 = "\((.*) \+.*"
            frm2 = re.match(pattern2, frm)
            if frm2 is None:
                return orig_tooltip
            frm = frm2.group(1)
        to = match.group(3)
        val_type = 'value'
        if to == 'True' or to == 'False':
            val_type = 'fit'
        tooltip = "'{}' {} change from {} to {}".format(param, val_type, frm, to)
        return tooltip

    @Slot()
    def resetUndoRedoStack(self):
        if borg.stack.enabled:
            borg.stack.clear()
            self.undoRedoChanged.emit()

    ####################################################################################################################
    # Reset state
    ####################################################################################################################

    @Property(bool, notify=projectCreatedChanged)
    def projectCreated(self):
        return self._project_created

    @projectCreated.setter
    def projectCreated(self, created: bool):
        if self._project_created == created:
            return

        self._project_created = created
        self.projectCreatedChanged.emit()

    @Slot()
    def resetState(self):
        pass
        # Need to be reimplemented for EasyReflectometry
        #self._project_info = self._defaultProjectInfo()
        #self.projectCreated = False
        #self.projectInfoChanged.emit()
        #self.project_save_filepath = ""
        #self.removeExperiment()
        #self.removePhase(self._sample.phases[self.currentPhaseIndex].name)
        #self.resetUndoRedoStack()
        #self.stateChanged.emit(False)


def createFile(path, content):
    if os.path.exists(path):
        print(f'File already exists {path}. Overwriting...')
        os.unlink(path)
    try:
        message = f'create file {path}'
        with open(path, "w") as file:
            file.write(content)
    except Exception as exception:
        print(message, exception)
