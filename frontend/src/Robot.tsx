import { Suspense, useRef, Component, type ReactNode } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { RoundedBox, Float, OrbitControls, Edges } from '@react-three/drei';
import * as THREE from 'three';
type V3=[number,number,number];
function Shell({position,scale,radius=.2}:{position:V3,scale:V3,radius?:number}){
 return <RoundedBox position={position} args={scale} radius={radius} smoothness={5}><meshPhysicalMaterial color="#d1caee" transparent opacity={.95} metalness={.45} roughness={.24} clearcoat={1} /><Edges threshold={22} color="#c7c4ff" transparent opacity={.25}/></RoundedBox>
}
function Bot({motion}:{motion:boolean}){
 const group=useRef<THREE.Group>(null);
 useFrame(({clock})=>{if(group.current&&motion)group.current.rotation.y=Math.sin(clock.elapsedTime*.3)*.2-.25});
 return <Float speed={motion?1.8:0} rotationIntensity={motion?.07:0} floatIntensity={motion?.35:0}><group ref={group} rotation={[.04,-.25,.025]}>
 <Shell position={[0,1.05,0]} scale={[1.95,1.35,1.16]} radius={.32}/>
 <RoundedBox position={[0,1.04,.57]} args={[1.65,.88,.17]} radius={.24} smoothness={5}><meshPhysicalMaterial color="#171c35" metalness={.4} roughness={.16} clearcoat={1}/></RoundedBox>
 {[-.43,.43].map(x=><group key={x} position={[x,1.1,.685]}><RoundedBox args={[.25,.32,.045]} radius={.11} smoothness={5}><meshBasicMaterial color="#a4f9ff"/></RoundedBox><mesh position={[0,0,-.025]}><sphereGeometry args={[.22,24,16]}/><meshBasicMaterial color="#6edcf4" transparent opacity={.08}/></mesh></group>)}
 <mesh position={[0,.86,.68]}><torusGeometry args={[.14,.015,8,32,Math.PI]}/><meshBasicMaterial color="#8edbe9"/></mesh>
 {[-1,1].map(side=><group key={side}>
 <mesh position={[side*1.04,1.05,0]} rotation={[0,0,Math.PI/2]}><cylinderGeometry args={[.3,.3,.15,32]}/><meshStandardMaterial color="#8f88ca" metalness={.75} roughness={.22}/></mesh>
 <mesh position={[side*1.135,1.05,0]} rotation={[0,Math.PI/2,0]}><torusGeometry args={[.22,.027,12,40]}/><meshBasicMaterial color="#b6e9ff"/></mesh>
 <group position={[side*1.12,-.55,0]} rotation={[0,0,side*.23]}><Shell position={[0,0,0]} scale={[.4,1.05,.53]} radius={.19}/><mesh position={[0,-.59,0]}><sphereGeometry args={[.22,24,20]}/><meshStandardMaterial color="#a9a2d7" metalness={.6} roughness={.25}/></mesh></group>
 </group>)}
 <mesh position={[0,.27,0]}><cylinderGeometry args={[.26,.31,.28,32]}/><meshStandardMaterial color="#77759b" metalness={.8} roughness={.22}/></mesh>
 <Shell position={[0,-.65,0]} scale={[1.55,1.52,.98]} radius={.32}/>
 <mesh position={[0,-.47,.51]}><circleGeometry args={[.32,48]}/><meshStandardMaterial color="#282947" metalness={.6} roughness={.2}/></mesh>
 <mesh position={[0,-.47,.525]}><torusGeometry args={[.24,.023,12,64]}/><meshBasicMaterial color="#99ecff"/></mesh>
 <mesh position={[0,-.47,.54]}><octahedronGeometry args={[.13]}/><meshBasicMaterial color="#ccc2ff"/></mesh>
 {[-.14,0,.14].map(x=><mesh key={x} position={[x,-1.03,.49]}><sphereGeometry args={[.025,12,8]}/><meshBasicMaterial color="#c5b6ff"/></mesh>)}
 <mesh position={[0,-1.48,0]}><cylinderGeometry args={[.47,.33,.16,48]}/><meshStandardMaterial color="#77709b" metalness={.8} roughness={.2}/></mesh>
 <mesh position={[0,-1.57,0]} rotation={[Math.PI/2,0,0]}><torusGeometry args={[.31,.035,12,64]}/><meshBasicMaterial color="#a1eaff"/></mesh>
 {[0,1,2].map(i=><mesh key={i} position={[0,-1.72-i*.14,0]} rotation={[-Math.PI/2,0,0]}><ringGeometry args={[.2+i*.07,.22+i*.07,64]}/><meshBasicMaterial color="#a8a7ff" transparent opacity={.35-i*.08} side={THREE.DoubleSide}/></mesh>)}
 </group></Float>
}
class Boundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return{failed:true}};render(){return this.state.failed?<div className="robot-fallback">◎</div>:this.props.children}}
export default function Robot({motion}:{motion:boolean}){
 return <Boundary><Canvas camera={{position:[0,.3,7.1],fov:42}} dpr={[1,1.5]} gl={{antialias:true,alpha:true}}><ambientLight intensity={1.4}/><directionalLight position={[3,5,4]} intensity={3} color="#e1d8ff"/><pointLight position={[-3,0,3]} intensity={16} color="#83dcff"/><pointLight position={[2,-1,-2]} intensity={18} color="#9a7dff"/><Suspense fallback={null}><Bot motion={motion}/>{[1.25,1.5,1.75].map((r,i)=><mesh key={r} position={[0,-2.25-i*.025,0]} rotation={[-Math.PI/2,0,0]}><ringGeometry args={[r,r+.012,100]}/><meshBasicMaterial color="#b9b3ff" transparent opacity={.4-i*.1} side={THREE.DoubleSide}/></mesh>)}</Suspense><OrbitControls enableZoom={false} enablePan={false} minPolarAngle={1.15} maxPolarAngle={1.85}/></Canvas></Boundary>
}
