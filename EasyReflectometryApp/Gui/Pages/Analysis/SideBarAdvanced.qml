import QtQuick 2.13
import QtQuick.Controls 2.13
import QtQuick.XmlListModel 2.13

import easyApp.Gui.Style 1.0 as EaStyle
import easyApp.Gui.Elements 1.0 as EaElements
import easyApp.Gui.Components 1.0 as EaComponents

import Gui.Globals 1.0 as ExGlobals
import Gui.Components 1.0 as ExComponents

EaComponents.SideBarColumn {
    

    EaElements.GroupBox {
        title: qsTr("Calculation")
        collapsed: false

        Row {
            spacing: EaStyle.Sizes.fontPixelSize

            // Minimizer
            EaComponents.TableViewLabel{
                horizontalAlignment: Text.AlignRight
                width: EaStyle.Sizes.fontPixelSize * 5.0
                text: qsTr("Engine:")
            }
            EaElements.ComboBox {
                width: minimizerSelector.width
                model: ExGlobals.Constants.proxy.calculator.calculatorNames
                currentIndex: ExGlobals.Constants.proxy.calculator.currentCalculatorIndex
                onCurrentIndexChanged: ExGlobals.Constants.proxy.calculator.currentCalculatorIndex = currentIndex
                Component.onCompleted: ExGlobals.Variables.calculatorSelector = this
            }
        }
    }

    EaElements.GroupBox {
        title: qsTr("Minimization")
        enabled: ExGlobals.Constants.proxy.data.experimentLoaded
        //collapsed: false

        Row {
            spacing: EaStyle.Sizes.fontPixelSize

            // Minimizer
            EaComponents.TableViewLabel{
                id: minimizerLabel

                horizontalAlignment: Text.AlignRight
                width: EaStyle.Sizes.fontPixelSize * 5.0
                text: qsTr("Minimizer:")
            }
            EaElements.ComboBox {
                id: minimizerSelector

                width: (EaStyle.Sizes.sideBarContentWidth - minimizerLabel.width * 2 - EaStyle.Sizes.fontPixelSize * 4) / 2

                model: ExGlobals.Constants.proxy.minimizer.minimizerNames
                currentIndex: ExGlobals.Constants.proxy.minimizer.currentMinimizerIndex

                onCurrentIndexChanged: {
                    ExGlobals.Constants.proxy.minimizer.currentMinimizerIndex = currentIndex
                }
            }

            // Spacer
            Item {}

            // Method
            EaComponents.TableViewLabel{
                horizontalAlignment: Text.AlignRight
                width: minimizerLabel.width
                text: qsTr("Method:")
            }
            EaElements.ComboBox {
                id: methodSelector

                width: minimizerSelector.width
                model: ExGlobals.Constants.proxy.minimizer.minimizerMethodNames
                currentIndex: ExGlobals.Constants.proxy.minimizer.currentMinimizerMethodIndex
                onCurrentIndexChanged: {
                    ExGlobals.Constants.proxy.currentMinimizerMethodIndex = currentIndex
                }
            }
        }

    }

    /*
    EaElements.GroupBox {
        title: qsTr("Plot settings")
        //collapsed: false

        Row {
            spacing: EaStyle.Sizes.fontPixelSize

            EaElements.CheckBox {
                text: qsTr("Show legend")
                checked: ExGlobals.Variables.showLegend
                onCheckedChanged: ExGlobals.Variables.showLegend = checked
            }

            EaElements.CheckBox {
                text: qsTr("Show measured")
                checked: ExGlobals.Constants.proxy.showMeasuredSeries
                onCheckedChanged: ExGlobals.Constants.proxy.showMeasuredSeries = checked
            }

            EaElements.CheckBox {
                text: qsTr("Show difference")
                checked: ExGlobals.Constants.proxy.showDifferenceChart
                onCheckedChanged: ExGlobals.Constants.proxy.showDifferenceChart = checked
            }
        }
    }
    */

    /*
    EaElements.GroupBox {
        title: qsTr("Parameters")
        last: true
        //collapsed: false

        EaElements.CheckBox {
            topPadding: 0
            text: qsTr("Iconified names")
            checked: ExGlobals.Variables.iconifiedNames
            onCheckedChanged: ExGlobals.Variables.iconifiedNames = checked
        }
    }
    */

    EaElements.GroupBox {
        title: qsTr("Plot")
        //enabled: true
        //collapsible: false
        last: true

        EaElements.CheckBox {
            topPadding: 0
            checked: ExGlobals.Constants.proxy.plotting1d.sldXDataReversed
            text: qsTr("Reverse SLD z-axis")
            ToolTip.text: qsTr("Checking this box will reverce the z-axis of the SLD plot")
            onToggled: ExGlobals.Constants.proxy.plotting1d.reverseSldXData()
        }

        EaElements.CheckBox {
            topPadding: 0
            id: rq4
            checked: ExGlobals.Constants.proxy.simulation.plotRQ4
            text: qsTr("Show R(q)q⁴")
            onToggled: ExGlobals.Constants.proxy.simulation.setPlotRQ4()
        }
    }

}
