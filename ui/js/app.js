import {
    Cephalon
} from "./cephalon.js";


/* =========================================
   START APPLICATION
========================================= */

const cephalonElement =
    document.getElementById(
        "cephalon"
    );


const stateLabel =
    document.getElementById(
        "state-label"
    );


const cephalon =
    new Cephalon(
        cephalonElement
    );


/* =========================================
   DEVELOPMENT CONTROLS
========================================= */

const stateButtons =
    document.querySelectorAll(
        "[data-state]"
    );


stateButtons.forEach(
    button => {

        button.addEventListener(
            "click",
            () => {

                const state =
                    button.dataset.state;


                cephalon.setState(
                    state
                );

            }
        );

    }
);


/* =========================================
   STATE UI FEEDBACK
========================================= */

cephalonElement.addEventListener(
    "cephalon-state-change",
    event => {

        const state =
            event.detail.state;


        stateLabel.textContent =
            state.toUpperCase();


        console.log(
            `[S-7] State → ${state}`
        );

    }
);


/* =========================================
   TEMP DEBUG ACCESS

   Permite probar desde la consola:

   cephalon.setState("thinking")
========================================= */

window.cephalon =
    cephalon;


console.log(
    "S-7 Cephalon UI initialized."
);