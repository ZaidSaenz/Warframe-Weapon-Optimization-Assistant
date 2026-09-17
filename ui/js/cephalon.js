export class Cephalon {

    constructor(element) {

        if (!element) {
            throw new Error(
                "Cephalon root element not found."
            );
        }


        this.element =
            element;


        this.states = [
            "idle",
            "listening",
            "thinking",
            "speaking",
            "warning"
        ];


        this.state =
            "idle";


        this.setState(
            "idle"
        );
    }


    setState(nextState) {

        if (
            !this.states.includes(
                nextState
            )
        ) {

            console.warn(
                `Unknown Cephalon state: ${nextState}`
            );

            return;
        }


        /*
         * Remove previous state classes
         */

        for (
            const state
            of this.states
        ) {

            this.element.classList.remove(
                `state-${state}`
            );

        }


        /*
         * Add new state
         */

        this.element.classList.add(
            `state-${nextState}`
        );


        this.state =
            nextState;


        /*
         * Notify other parts of the UI
         */

        this.element.dispatchEvent(

            new CustomEvent(
                "cephalon-state-change",
                {
                    detail: {
                        state:
                            nextState
                    }
                }
            )

        );

    }


    getState() {

        return this.state;

    }

}