import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import DesktopBootstrap from "./components/DesktopBootstrap";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <DesktopBootstrap><App /></DesktopBootstrap>
  </React.StrictMode>,
);
