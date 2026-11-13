import { Route, Routes } from 'react-router-dom';
import { AppShell } from './components/AppShell';
import Dashboard from './pages/Dashboard';
import RequisitionsList from './pages/requisitions/RequisitionsList';
import RequisitionDetail from './pages/requisitions/RequisitionDetail';
import ScreeningList from './pages/screening/ScreeningList';
import ScreeningDetail from './pages/screening/ScreeningDetail';
import Interviews from './pages/interviews/Interviews';
import Offers from './pages/offers/Offers';

function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/requisitions" element={<RequisitionsList />} />
        <Route path="/requisitions/:id" element={<RequisitionDetail />} />
        <Route path="/screening" element={<ScreeningList />} />
        <Route path="/screening/:id" element={<ScreeningDetail />} />
        <Route path="/interviews" element={<Interviews />} />
        <Route path="/offers" element={<Offers />} />
      </Routes>
    </AppShell>
  );
}

export default App;
