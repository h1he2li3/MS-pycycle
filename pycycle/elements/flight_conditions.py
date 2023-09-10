import openmdao.api as om

# from pycycle.thermo.cea import species_data # not used anywhere so i disabled to see if this what is causing the error not to generate N2 diagram
from pycycle.constants import THERMO_DEFAULT_COMPOSITIONS
from pycycle.elements.ambient import Ambient
from pycycle.elements.flow_start import FlowStart
from pycycle.thermo.thermo import ThermoAdd, Thermo
from pycycle.element_base import Element


class FlightConditions(Element):
    """Determines total and static flow properties given an altitude and Mach number using the input atmosphere model

    Flows are apparently divided into: primary and

    Framework:
    ---------
    def initialize():, def pyc_setup_output_ports():, def setup(): under FlightConditions
    Just MainClass with some outside imports

    Inputs:
    ------

    MN = Mach Number []
    alt = Altitude [ft]
    W = [ft/s]
    dTs = [degR]



    """

    def initialize(self):
        """
        Here, compositionm, reactant and mix_ratio_name options are declared.

        composition means the composition of the inlet flow whether air or fuel/air mixture.
        reactant is of two types: bool and str. bool is False, then no air and fuel is mixed, and flow is just air.
        mix_ratio is the input that governs the amount of fuel that is mixed into the primary flow.
        """
        # Composition of fluid flow as in fuel-air mixture or just fuel or just air?
        self.options.declare("composition", default=None,
            desc="composition of the flow. If None, default for thermo package is used",)
        # Base composition mean the composition of the fuel?
        self.options.declare("reactant", default=False, types=(bool, str),
            desc="If False, flow matches base composition. If a string, then that reactant "
            "is mixed into the flow at at the ratio set by the `mix_ratio` input",)
        self.options.declare("mix_ratio_name", default="mix:ratio",
            desc="The name of the input that governs the mix ratio of the reactant to the primary flow",)

        super().initialize()

    def pyc_setup_output_ports(self):
        """

        """
        composition = self.options["composition"]
        thermo_method = self.options["thermo_method"]
        thermo_data = self.options["thermo_data"]
        reactant = self.options["reactant"]

        if reactant is not False:  # This means reactant is mixed into the flow.
            # just make a local ThermoAdd, since the FS (FlowStart) will make the real one for us later
            # Local ThermoAdd object created to handle thermodynamics of handling a reactant addition. Configured with various parameters like method (CEA, TABULAR), thermodynamic data, composition of the inflow and composition of the reactant.
            thermo_add = ThermoAdd(
                method=thermo_method, mix_mode="reactant",
                thermo_kwargs={
                    "spec": thermo_data,
                    "inflow_composition": composition,
                    "mix_composition": reactant,},)
            # Output flow port Fl_0 is initialized to consider the fuel air mixing.
            self.init_output_flow("Fl_O", thermo_add)

        else:  # Without fuel mixing option. Just takes the composition of the airflow in. FAR = 0 in case of TABULAR and composition is some air comosition if CEA.
            if composition is None:
                composition = THERMO_DEFAULT_COMPOSITIONS[thermo_method]  # Takes in the composition based on the thermo_method.
            self.init_output_flow("Fl_O", composition)

    def setup(self):
        thermo_method = self.options["thermo_method"]
        thermo_data = self.options["thermo_data"]
        reactant = self.options["reactant"]
        mix_ratio_name = self.options["mix_ratio_name"]

        # composition = self.Fl_O_data['Fl_O']
        composition = self.options["composition"]

        # dTs is the delta from standard day temperature. alt is the altitude at which we are going to extract the Ts, Ps, and rhos
        self.add_subsystem("ambient", Ambient(), promotes=("alt", "dTs"))  # alt and dTs are inputs

        conv = self.add_subsystem("conv", om.Group(), promotes=["*"])  # promotes all
        if reactant is not False:
            proms = ["Fl_O:*", "MN", "W", mix_ratio_name]
        else:
            proms = ["Fl_O:*", "MN", "W"]
        fs_start = conv.add_subsystem("fs",
            FlowStart(
                thermo_method=thermo_method,
                thermo_data=thermo_data,
                composition=composition,
                reactant=reactant,
                mix_ratio_name=mix_ratio_name,
            ), promotes=proms,)

        # need to manually call this in this setup, because we have an element within an element
        fs_start.pyc_setup_output_ports()

        balance = conv.add_subsystem("balance", om.BalanceComp())
        balance.add_balance("Tt", val=500.0, lower=1e-4, units="degR", desc="Total temperature", eq_units="degR",)
        balance.add_balance("Pt", val=14.696, lower=1e-4, units="psi", desc="Total pressure", eq_units="psi",)
        # sub.set_order(['fs','balance'])

        newton = conv.nonlinear_solver = om.NewtonSolver()
        newton.options["atol"] = 1e-10
        newton.options["rtol"] = 1e-10
        newton.options["maxiter"] = 10
        newton.options["iprint"] = -1
        newton.options["solve_subsystems"] = True
        newton.options["reraise_child_analysiserror"] = False
        newton.linesearch = om.BoundsEnforceLS()
        newton.linesearch.options["bound_enforcement"] = "scalar"

        newton.linesearch.options["iprint"] = -1
        # newton.linesearch.options['solve_subsystems'] = True

        conv.linear_solver = om.DirectSolver(assemble_jac=True)

        self.connect("ambient.Ps", "balance.rhs:Pt")
        self.connect("ambient.Ts", "balance.rhs:Tt")

        self.connect("balance.Pt", "fs.P")
        self.connect("balance.Tt", "fs.T")

        self.connect("Fl_O:stat:P", "balance.lhs:Pt")
        self.connect("Fl_O:stat:T", "balance.lhs:Tt")

        # self.set_order(['ambient', 'subgroup'])

        super().setup()


if __name__ == "__main__":
    p1 = om.Problem()
    p1.model = om.Group()

    # The whole deal about connecting IndepVarComp() is avoided in newer versions of OpenMDAO and the whole connection can also be ignored.
    des_vars = p1.model.add_subsystem("des_vars", om.IndepVarComp())
    des_vars.add_output("W", 0.0, units="lbm/s")
    des_vars.add_output("alt", 1.0, units="ft")
    des_vars.add_output("MN", 0.5)
    des_vars.add_output("dTs", 0.0, units="degR")

    fc = p1.model.add_subsystem("fc", FlightConditions())

    p1.model.connect("des_vars.W", "fc.W")
    p1.model.connect("des_vars.alt", "fc.alt")
    p1.model.connect("des_vars.MN", "fc.MN")
    p1.model.connect("des_vars.dTs", "fc.dTs")

    p1.setup()

    # p1.root.list_connections()

    p1["des_vars.alt"] = 17868.79060515557
    p1["des_vars.MN"] = 2.101070288213628
    p1["des_vars.dTs"] = 0.0
    p1["des_vars.W"] = 1.0

    p1.run_model()

    print("Ts_atm: ", p1["fc.ambient.Ts"])
    print("Ts_set: ", p1["fc.Fl_O:stat:T"])
    print("Ps_atm: ", p1["fc.ambient.Ps"])
    print("Ps_set: ", p1["fc.Fl_O:stat:P"])
    print("rhos_atm: ", p1["fc.ambient.rhos"] * 32.175)
    print("rhos_set: ", p1["fc.Fl_O:stat:rho"])
    print("W", p1["fc.Fl_O:stat:W"])

    print("Pt: ", p1["fc.Fl_O:tot:P"])
