import openmdao.api as om

from pycycle.elements.US1976 import USatm1976Comp


class DeltaTs(om.ExplicitComponent):
    """Computes temperature based on delta from atmospheric"""

    def setup(self):
        # inputs

        # They use some unit called `degree Rankine`. Needs to be looked at carefully on how it varies with Kelvin.
        # 1 K = 5/9 dR. So, 500 dR is ~278 K.
        self.add_input(
            "Ts_in", val=500.0, units="degR", desc="Temperature from atmospheric model"
        )
        self.add_input(
            "dTs", val=0.0, units="degR", desc="Delta from standard day temperature"
        )

        self.add_output("Ts", shape=1, units="degR", desc="Temperature with delta")

        self.declare_partials("Ts", ["Ts_in", "dTs"], val=1.0)

    def compute(self, inputs, outputs):
        outputs["Ts"] = inputs["Ts_in"] + inputs["dTs"]

    def compute_partials(self, inputs, partials):
        pass


class Ambient(om.Group):
    """Determines pressure, temperature and density base on altitude from an input standard atmosphere table"""

    def setup(self):
        # alt in [ft], Ps in [psi], and rho in [slug/ft**3]. The USatm1976Comp has .alt, .T, .P, .rho, .a, .viscosity. It is still not clear is Ps and P are the same the code is trying to take the USatm1976Comp.P as Ps here.

        # Should replace promotes with promotes inputs and outputs because this is confusing.
        readAtm = self.add_subsystem(
            "readAtmTable", USatm1976Comp(), promotes=("alt", "Ps", "rhos")
        )

        self.add_subsystem("dTs", DeltaTs(), promotes=("dTs", "Ts"))
        self.connect("readAtmTable.Ts", "dTs.Ts_in")

        # self.set_order(['readAtmTable','dTs'])


# if __name__ == "__main__":

#     from pycycle.elements.US1976 import USatm1976Data

#     p1 = om.Problem()
#     p1.root = Ambient()

#     #This value can be changed by putting it in a loop and acts as an independent input. This is what we exactly do towards the end.
#     var = (('alt', 30000.0),)
#     p1.root.add("idv", om.IndepVarComp(var), promotes=["*"])

#     p1.setup()

#     p1.run()

#     # p1.check_partials()
#     # print('Ts: ', p1['Ts'])
#     # print('Ps: ', p1['Ps'])
#     # print('rhos: ', p1['rhos'])

#     T = USatm1976Data.T
#     P = USatm1976Data.P
#     rho = USatm1976Data.rho

#     # Takes in altitude and also creates `i` variable for looping through all altitudes from USatm1976Data.alt
#     # for example, it takes an altitude and sends the altitude to the OpenMDAO problem that is setup, then the OpenMDAO problem runs which generates the output pressure, tenperature and density at the given altitude.

#     for i, alt in enumerate(USatm1976Data.alt):
#         p1['alt'] = alt
#         p1.run()
#         print(10*"=")
#         print("Ts", p1['Ts'], T[i])
#         print("Ps", p1['Ps'], P[i])
#         print("rho", p1['rhos'], rho[i])

#     p1.model.list_states()

# Changed the code to reflect the newer version of OpenMDAO
if __name__ == "__main__":
    from pycycle.elements.US1976 import USatm1976Data

    p1 = om.Problem()
    p1.model = Ambient()

    # Adding an independent variable for altitude
    p1.model.add_subsystem(
        "idv", om.IndepVarComp("alt", 30000.0, units="ft"), promotes=["*"]
    )

    p1.setup()

    T = USatm1976Data.T
    P = USatm1976Data.P
    rho = USatm1976Data.rho

    # Looping through all altitudes from USatm1976Data.alt
    for i, alt in enumerate(USatm1976Data.alt):
        p1.set_val("alt", alt)  # Setting the altitude value
        p1.run_model()  # Running the OpenMDAO problem

        print(10 * "=")
        print("Ts", p1.get_val("Ts"), T[i])
        print("Ps", p1.get_val("Ps"), P[i])
        print("rho", p1.get_val("rhos"), rho[i])

    # If you want to print or analyze the states, you can do so here
    # For example, you can print the final values:
    print("Final Ts:", p1.get_val("Ts"))
    print("Final Ps:", p1.get_val("Ps"))
    print("Final rho:", p1.get_val("rhos"))
