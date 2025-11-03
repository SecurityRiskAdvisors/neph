import { runSimulation, type Simulation } from "@cloud-copilot/iam-simulate"
import express, { Express, Request, Response } from "express";
import bodyParser from "body-parser"

const app: Express = express();
app.use(express.json());
const port = 3000;


async function runSimFromJson(simJson: Simulation){
    const simulation = simJson as Simulation;
    console.log(JSON.stringify(simulation));
    let result = await runSimulation(simulation, {});
    if (result.errors) {
        let error = JSON.stringify(result.errors);
        console.log(error)
        return error
    } else {
        if (result.analysis) {
            let analysis = JSON.stringify(result.analysis);
            console.log(analysis);
            return analysis
        } else {
            return JSON.stringify({message: "unknown"})
        }
    }
}


app.post("/",  async (req: Request, res: Response) => {
    //console.log(req.body);
    let ret = await runSimFromJson(req.body);
    res.send(ret);
});

app.listen(port, () => {
    console.log("started");
});
